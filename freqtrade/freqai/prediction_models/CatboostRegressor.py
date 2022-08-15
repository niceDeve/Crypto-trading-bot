import gc
import logging
from typing import Any, Dict

from catboost import CatBoostRegressor, Pool

from freqtrade.freqai.prediction_models.BaseRegressionModel import BaseRegressionModel


logger = logging.getLogger(__name__)


class CatboostRegressor(BaseRegressionModel):
    """
    User created prediction model. The class needs to override three necessary
    functions, predict(), train(), fit(). The class inherits ModelHandler which
    has its own DataHandler where data is held, saved, loaded, and managed.
    """

    def fit(self, data_dictionary: Dict[str, Any], pair: str = '') -> Any:
        """
        User sets up the training and test data to fit their desired model here
        :param data_dictionary: the dictionary constructed by DataHandler to hold
                                all the training and test data/labels.
        """

        train_data = Pool(
            data=data_dictionary["train_features"],
            label=data_dictionary["train_labels"],
            weight=data_dictionary["train_weights"],
        )
        if self.freqai_info.get('data_split_parameters', {}).get('test_size', 0.1) == 0:
            test_data = None
        else:
            test_data = Pool(
                data=data_dictionary["test_features"],
                label=data_dictionary["test_labels"],
                weight=data_dictionary["test_weights"],
            )

        model = CatBoostRegressor(
            allow_writing_files=False,
            **self.model_training_parameters,
        )

        model.fit(X=train_data, eval_set=test_data)

        # some evidence that catboost pools have memory leaks:
        # https://github.com/catboost/catboost/issues/1835
        del train_data, test_data
        gc.collect()

        return model
