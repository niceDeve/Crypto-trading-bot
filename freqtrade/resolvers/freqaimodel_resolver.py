# pragma pylint: disable=attribute-defined-outside-init

"""
This module load a custom model for freqai
"""
import logging
from pathlib import Path
from typing import Dict

from freqtrade.constants import USERPATH_FREQAIMODELS
from freqtrade.exceptions import OperationalException
from freqtrade.freqai.freqai_interface import IFreqaiModel
from freqtrade.resolvers import IResolver


logger = logging.getLogger(__name__)


class FreqaiModelResolver(IResolver):
    """
    This class contains all the logic to load custom hyperopt loss class
    """

    object_type = IFreqaiModel
    object_type_str = "FreqaiModel"
    user_subdir = USERPATH_FREQAIMODELS
    initial_search_path = Path(__file__).parent.parent.joinpath("optimize").resolve()

    @staticmethod
    def load_freqaimodel(config: Dict) -> IFreqaiModel:
        """
        Load the custom class from config parameter
        :param config: configuration dictionary
        """

        freqaimodel_name = config.get("freqaimodel")
        if not freqaimodel_name:
            raise OperationalException(
                "No freqaimodel set. Please use `--freqaimodel` to "
                "specify the FreqaiModel class to use.\n"
            )
        freqaimodel = FreqaiModelResolver.load_object(
            freqaimodel_name,
            config,
            kwargs={"config": config},
            extra_dir=config.get("freqaimodel_path"),
        )

        return freqaimodel
