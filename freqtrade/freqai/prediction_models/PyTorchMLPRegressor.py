from typing import Any, Dict

import torch

from freqtrade.freqai.base_models.PyTorchModelTrainer import PyTorchModelTrainer
from freqtrade.freqai.data_kitchen import FreqaiDataKitchen
from freqtrade.freqai.prediction_models.PyTorchMLPModel import PyTorchMLPModel
from freqtrade.freqai.prediction_models.PyTorchRegressor import PyTorchRegressor


class PyTorchMLPRegressor(PyTorchRegressor):
    """
    This class implements the fit method of IFreqaiModel.
    in the fit method we initialize the model and trainer objects.
    the only requirement from the model is to be aligned to PyTorchRegressor
    predict method that expects the model to predict tensor of type float.
    the trainer defines the training loop.

    parameters are passed via `model_training_parameters` under the freqai
    section in the config file. e.g:
    {
        ...
        "freqai": {
            ...
            "model_training_parameters" : {
                "learning_rate": 3e-4,
                "trainer_kwargs": {
                    "max_iters": 5000,
                    "batch_size": 64,
                    "max_n_eval_batches": None,
                },
                "model_kwargs": {
                    "hidden_dim": 512,
                    "dropout_percent": 0.2,
                    "n_layer": 1,
                },
            }
        }
    }
    """

    def __init__(
            self,
            learning_rate: float = 3e-4,
            model_kwargs: Dict[str, Any] = {},
            trainer_kwargs: Dict[str, Any] = {},
            **kwargs
    ):
        super().__init__(**kwargs)
        config = self.freqai_info.get("model_training_parameters", {})
        self.learning_rate: float = config.get("learning_rate", learning_rate)
        self.model_kwargs: Dict[str, any] = config.get("model_kwargs", model_kwargs)
        self.trainer_kwargs: Dict[str, any] = config.get("trainer_kwargs", trainer_kwargs)

    def fit(self, data_dictionary: Dict, dk: FreqaiDataKitchen, **kwargs) -> Any:
        """
        User sets up the training and test data to fit their desired model here
        :param data_dictionary: the dictionary constructed by DataHandler to hold
                                all the training and test data/labels.
        """

        n_features = data_dictionary["train_features"].shape[-1]
        model = PyTorchMLPModel(
            input_dim=n_features,
            output_dim=1,
            **self.model_kwargs
        )
        model.to(self.device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=self.learning_rate)
        criterion = torch.nn.MSELoss()
        init_model = self.get_init_model(dk.pair)
        trainer = PyTorchModelTrainer(
            model=model,
            optimizer=optimizer,
            criterion=criterion,
            device=self.device,
            init_model=init_model,
            target_tensor_type=torch.float,
            **self.trainer_kwargs,
        )
        trainer.fit(data_dictionary)
        return trainer
