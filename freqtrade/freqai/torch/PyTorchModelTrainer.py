import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import torch
from torch import nn
from torch.optim import Optimizer
from torch.utils.data import DataLoader, TensorDataset

from freqtrade.freqai.torch.PyTorchDataConvertor import PyTorchDataConvertor
from freqtrade.freqai.torch.PyTorchTrainerInterface import PyTorchTrainerInterface

from .datasets import WindowDataset


logger = logging.getLogger(__name__)


class PyTorchModelTrainer(PyTorchTrainerInterface):
    def __init__(
            self,
            model: nn.Module,
            optimizer: Optimizer,
            criterion: nn.Module,
            device: str,
            data_convertor: PyTorchDataConvertor,
            model_meta_data: Dict[str, Any] = {},
            window_size: int = 1,
            tb_logger: Any = None,
            **kwargs
    ):
        """
        :param model: The PyTorch model to be trained.
        :param optimizer: The optimizer to use for training.
        :param criterion: The loss function to use for training.
        :param device: The device to use for training (e.g. 'cpu', 'cuda').
        :param init_model: A dictionary containing the initial model/optimizer
            state_dict and model_meta_data saved by self.save() method.
        :param model_meta_data: Additional metadata about the model (optional).
        :param data_convertor: convertor from pd.DataFrame to torch.tensor.
        :param max_iters: used to calculate n_epochs. The number of training iterations to run.
            iteration here refers to the number of times optimizer.step() is called.
            ignored if n_epochs is set.
        :param n_epochs: The maximum number batches to use for evaluation.
        :param batch_size: The size of the batches to use during training.
        """
        self.model = model
        self.optimizer = optimizer
        self.criterion = criterion
        self.model_meta_data = model_meta_data
        self.device = device
        self.max_iters: int = kwargs.get("max_iters", None)
        self.n_epochs: Optional[int] = kwargs.get("n_epochs", 10)
        if not self.max_iters and not self.n_epochs:
            raise Exception("Either `max_iters` or `n_epochs` should be set.")

        self.batch_size: int = kwargs.get("batch_size", 64)
        self.data_convertor = data_convertor
        self.window_size: int = window_size
        self.tb_logger = tb_logger
        self.test_batch_counter = 0

    def fit(self, data_dictionary: Dict[str, pd.DataFrame], splits: List[str]):
        """
        :param data_dictionary: the dictionary constructed by DataHandler to hold
        all the training and test data/labels.
        :param splits: splits to use in training, splits must contain "train",
        optional "test" could be added by setting freqai.data_split_parameters.test_size > 0
        in the config file.

         - Calculates the predicted output for the batch using the PyTorch model.
         - Calculates the loss between the predicted and actual output using a loss function.
         - Computes the gradients of the loss with respect to the model's parameters using
           backpropagation.
         - Updates the model's parameters using an optimizer.
        """
        self.model.train()

        data_loaders_dictionary = self.create_data_loaders_dictionary(data_dictionary, splits)
        n_obs = len(data_dictionary["train_features"])
        n_epochs = self.n_epochs or self.calc_n_epochs(
            n_obs=n_obs,
            batch_size=self.batch_size,
            n_iters=self.max_iters,
        )

        batch_counter = 0
        for _ in range(n_epochs):
            for _, batch_data in enumerate(data_loaders_dictionary["train"]):
                xb, yb = batch_data
                xb = xb.to(self.device)
                yb = yb.to(self.device)
                yb_pred = self.model(xb)
                loss = self.criterion(yb_pred, yb)

                self.optimizer.zero_grad(set_to_none=True)
                loss.backward()
                self.optimizer.step()
                self.tb_logger.log_scalar("train_loss", loss.item(), batch_counter)
                batch_counter += 1

            # evaluation
            if "test" in splits:
                self.estimate_loss(data_loaders_dictionary, "test")

    @torch.no_grad()
    def estimate_loss(
            self,
            data_loader_dictionary: Dict[str, DataLoader],
            split: str,
    ) -> None:
        self.model.eval()
        for _, batch_data in enumerate(data_loader_dictionary[split]):
            xb, yb = batch_data
            xb.to(self.device)
            yb.to(self.device)

            yb_pred = self.model(xb)
            loss = self.criterion(yb_pred, yb)
            self.tb_logger.log_scalar(f"{split}_loss", loss.item(), self.test_batch_counter)
            self.test_batch_counter += 1

        self.model.train()

    def create_data_loaders_dictionary(
            self,
            data_dictionary: Dict[str, pd.DataFrame],
            splits: List[str]
    ) -> Dict[str, DataLoader]:
        """
        Converts the input data to PyTorch tensors using a data loader.
        """
        data_loader_dictionary = {}
        for split in splits:
            x = self.data_convertor.convert_x(data_dictionary[f"{split}_features"], self.device)
            y = self.data_convertor.convert_y(data_dictionary[f"{split}_labels"], self.device)
            dataset = TensorDataset(x, y)
            data_loader = DataLoader(
                dataset,
                batch_size=self.batch_size,
                shuffle=True,
                drop_last=True,
                num_workers=0,
            )
            data_loader_dictionary[split] = data_loader

        return data_loader_dictionary

    @staticmethod
    def calc_n_epochs(n_obs: int, batch_size: int, n_iters: int) -> int:
        """
        Calculates the number of epochs required to reach the maximum number
        of iterations specified in the model training parameters.

        the motivation here is that `max_iters` is easier to optimize and keep stable,
        across different n_obs - the number of data points.
        """

        n_batches = n_obs // batch_size
        n_epochs = min(n_iters // n_batches, 1)
        if n_epochs <= 10:
            logger.warning(
                f"Setting low n_epochs: {n_epochs}. "
                f"Please consider increasing `max_iters` hyper-parameter."
            )

        return n_epochs

    def save(self, path: Path):
        """
        - Saving any nn.Module state_dict
        - Saving model_meta_data, this dict should contain any additional data that the
          user needs to store. e.g. class_names for classification models.
        """

        torch.save({
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "model_meta_data": self.model_meta_data,
            "pytrainer": self
        }, path)

    def load(self, path: Path, device: Optional[str] = None):
        checkpoint = torch.load(path, map_location=device)
        return self.load_from_checkpoint(checkpoint)

    def load_from_checkpoint(self, checkpoint: Dict):
        """
        when using continual_learning, DataDrawer will load the dictionary
        (containing state dicts and model_meta_data) by calling torch.load(path).
        you can access this dict from any class that inherits IFreqaiModel by calling
        get_init_model method.
        """
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        self.model_meta_data = checkpoint["model_meta_data"]
        return self


class PyTorchTransformerTrainer(PyTorchModelTrainer):
    """
    Creating a trainer for the Transformer model.
    """

    def create_data_loaders_dictionary(
            self,
            data_dictionary: Dict[str, pd.DataFrame],
            splits: List[str]
    ) -> Dict[str, DataLoader]:
        """
        Converts the input data to PyTorch tensors using a data loader.
        """
        data_loader_dictionary = {}
        for split in splits:
            x = self.data_convertor.convert_x(data_dictionary[f"{split}_features"], self.device)
            y = self.data_convertor.convert_y(data_dictionary[f"{split}_labels"], self.device)
            dataset = WindowDataset(x, y, self.window_size)
            data_loader = DataLoader(
                dataset,
                batch_size=self.batch_size,
                shuffle=False,
                drop_last=True,
                num_workers=0,
            )
            data_loader_dictionary[split] = data_loader

        return data_loader_dictionary
