import sys
from typing import Optional, Union

import pandas as pd
from musif.config import PostProcess_Configuration
from musif.process.utils import (delete_columns, delete_previous_items,
                                 join_keys, join_keys_modulatory,
                                 join_part_degrees, log_errors_and_shape,
                                 merge_duetos_trios, merge_single_voices,
                                 replace_nans, split_passion_A)
from pandas import DataFrame

sys.path.insert(0, "../musif")
import os

import numpy as np
from musif.common.sort import sort_columns
from musif.common.utils import read_dicts_from_csv
from musif.extract.features.composer.handler import COMPOSER
from musif.extract.features.core.constants import FILE_NAME
from musif.extract.features.file_name.constants import ARIA_ID, ARIA_LABEL
from musif.extract.features.harmony.constants import (KEY_MODULATORY,
                                                      CHORDS_GROUPING_prefix,
                                                      KEY_prefix)
from musif.extract.features.prefix import get_part_prefix, get_sound_prefix
from musif.extract.features.scoring.constants import INSTRUMENTATION, SCORING, VOICES
from musif.logs import perr, pinfo

from .constants import (PRESENCE, columns_order, label_by_col,
                        voices_list_prefixes)


class DataProcessor:
    """Processor class that treats columns and information of a DataFrame

    This operator processes information from a DataFrame or a .csv file. 
    It deletes unseful columns and merges those that are required to clean the data.
    The main method .process() returns a DataFrame and saves it into a .csv file.

    ...

    Attributes
    ----------
    data : DataFrame
        DataFrame extracted with FeaturesExtractor containing all info.
    info: str
        Path to .csv file or Dataframe containing the information from FeaturesExtractor

    Methods
    -------
    process_info(info=info: Union[str, DataFrame])
        Reads info and returns a DataFrame
    process()
        Processes all the DataFrame information and saves it to a .csv file
    assign_labels()
        Assigns labels from file Passion.csv to DataFrame according to AriaLabel column
    preprocess_data()
        Deletes columns with no information, convertes 0 to nan and depurates data
    group_columns()
        Groups thos columns related to Keys, Key_Modulatory and Degree for agregated analysis
    merge_voices()
        Joins every voice part into common columns startung with 'SoundVoice'. Also fixes duetos. 
    unbundle_instrumentation()
        Separates 'Instrumentation' column into several Presence_ columns for every instrument present in Instrumentation.
    delete_unwanted_columns(**kwargs)
        Deletes all columns that are not needed according to config.yml file  
    to_csv(dest_path: str)
        Saves final information to a csv file 
    """

    def __init__(self, *args, **kwargs):
        """
        Parameters
        ----------
        *args:  str
            Could be a path to a .yml file, a PostProcess_Configuration object or a dictionary. Length zero or one.
        *kwargs : str
            Key words arguments to construct 
        kwargs[info]: Union[str, DataFrame]
            Either a path to a .csv file containing the information either a DataFrame object fromm FeaturesExtractor
        """
        self._post_config=PostProcess_Configuration(*args, **kwargs)
        self.info=kwargs.get('info')
        self.data = self.process_info(self.info)

    def process_info(self, info: Union[str, DataFrame]) -> DataFrame:
        """
        Extracts the info from a directory to a csv file or from a Dataframe object. 
        
        Parameters
        ------
        info: str
            Info in the from of str (path to csv file) or DataFrame
        
        Raises
        ------
        FileNotFoundError
            If path to the .csv file is not found.

        Returns
        ------
            Dataframe with the information from either the file or the previous DataFrame.
        """
        try:
            if isinstance(info, str):
                pinfo('\nReading csv file...')
                if not os.path.exists(info):
                    raise FileNotFoundError("The .csv file doesn't exists!")
                self.destination_route=info.replace('.csv','')
                df = pd.read_csv(info, low_memory=False, sep=',', encoding_errors='replace')
                df[FILE_NAME].to_csv(self._post_config.check_file, index=False)
                return df
            
            elif isinstance(info, DataFrame):
                pinfo('\nProcessing DataFrame...')
                return df
        except FileNotFoundError:
            return pd.DataFrame()
        else:
            perr('Wrong info type! You must introduce either a DataFrame either the name of a .csv file.')

    def process(self) -> DataFrame:
        """
        Removes nan values, deletes unuseful columns
        and merges those that are needed according to config.yml file. Saves processed DataFrame 
        into a csv file.

        Returns
        ------
        Dataframe object        
        """

        if self._post_config.delete_files:
            delete_previous_items()
        
        self.assign_labels()
        pinfo('\nPreprocessing data...')
        self.preprocess_data()
        pinfo('\nScanning info looking for errors...')
        self._scan_dataframe()

        if self._post_config.unbundle_instrumentation:
            pinfo('\nSeparating "Instrumentation" column...')
            self.unbundle_instrumentation()
        
        if self._post_config.merge_voices:
            self.merge_voices()
            
        pinfo('\nDeleting not useful columns...')
        self.delete_unwanted_columns()

        if self._post_config.grouped_analysis:
            self.group_columns()

        self._final_data_processing()            
        return self.data

    def assign_labels(self) -> None:
        """Crosses passions labels from Passions.csv file with the DataFrame so every row (aria)
        gets assigned to its own Label
        """

        passions = read_dicts_from_csv("Passions.csv")
        data_by_aria_label = {label_data["Label"]: label_data for label_data in passions}
        for col, label in label_by_col.items():
            values = []
            for _, row in self.data.iterrows():
                data_by_aria = data_by_aria_label.get(row[ARIA_LABEL])
                label_value = data_by_aria[col] if data_by_aria else None
                values.append(label_value)
            self.data[label] = values

        if self._post_config.split_passionA:
            split_passion_A(self.data)
  
    def preprocess_data(self) -> None:
        """ Cleans data and removes columns with no information or rows without assigned Label
        """
        if 'Label_Passions' in self.data:
            del self.data['Label_Passions']
        if 'Label_Sentiment' in self.data:
            del self.data['Label_Sentiment']

        self.data = self.data[~self.data["Label_BasicPassion"].isnull()]
        self.data.replace(0.0, np.nan, inplace=True)
        self.data.dropna(axis=1, how='all', inplace=True)
        self.data.reset_index(inplace=True)

    def group_columns(self) -> None:
        """Groups Key_*_PercentageMeasures, Key_Modulatory and Degrees columns. Into bigger groups
        for agregated analysis, keeping the previous ones. Also deletes unnecesary columns for analysis.
        """

        self.data.drop([i for i in self.data.columns if 'Degree' in i and not '_relative' in i], axis = 1, inplace=True)
        self.data.drop([i for i in self.data.columns if i.startswith(CHORDS_GROUPING_prefix+'1')], axis = 1, inplace=True)
        self._group_keys_modulatory()
        self._group_keys()
        self._join_degrees()

    def merge_voices(self) -> None:
        """Finds multiple singers arias (duetos/trietos) and calculates mean, max or min between them.
        Unifies all voices columns into SoundVoice_ columns.  
        """
        pinfo('\nScaning voice columns...')
        generic_sound_voice_prefix = get_sound_prefix('Voice') 
        # Delete columns that contain strings 
        df_voices=self.data[[col for col in self.data.columns if any(substring in col for substring in voices_list_prefixes)]]
        cols_to_delete=df_voices.select_dtypes(include=['object']).columns
        self.data.drop(cols_to_delete, axis = 1, inplace=True)
        merge_duetos_trios(self.data, generic_sound_voice_prefix)
        merge_single_voices(self.data, generic_sound_voice_prefix)

    def unbundle_instrumentation(self) -> None:
        """Separates Instrumentation column into as many columns as instruments present in Instrumentation,
        assigning 1 for every instrument that is present and 0 if it is not for every row (aria).
        """
        
        for i, row in enumerate(self.data[INSTRUMENTATION]):
            for element in row.split(','):
                self.data.at[i, PRESENCE+'_'+element] = 1
        del self.data[INSTRUMENTATION]
        del self.data[SCORING]


    def delete_unwanted_columns(self, **kwargs) -> None:
        """Deletes not necessary columns for statistical analysis.

        If keyword arguments are passed in, they overwrite those found
        into configurationg file

        Parameters
        ----------
        **kwargs : str, optional
            Any value from config.yml can be overwritten by passing arguments
            to the method

        Raises
        ------
        KeyError
            If any of the columns required to delete is not found 
            in the original DataFrame.
        """
        config_data=self._post_config.to_dict_post()
        config_data.update(kwargs)  # Override values
        try:
            delete_columns(self.data, config_data)
        except KeyError:
            perr('Some columns are already not present in the Dataframe')
    
    def to_csv(self, dest_path: str) -> None:
        """Saves current information into a .csv file given the name onf dest_path
        
        Parameters
        ----------
        dest_path : str
            Path to the route where the .csv file needs to be stored.
        """

        self.data.to_csv(dest_path, index=False)
        pinfo(f'\nData succesfully saved as {dest_path} in current directory.')

    def _group_keys_modulatory(self) -> None:
        self.data.update(self.data[[i for i in self.data.columns if KEY_prefix+KEY_MODULATORY in i]].fillna(0))
        join_keys_modulatory(self.data)

    def _group_keys(self) -> None:
        self.data.update(self.data[[i for i in self.data.columns if KEY_prefix in i]].fillna(0))
        join_keys(self.data)

    def _join_degrees(self) -> None:
        total_degrees = [i for i in self.data.columns if '_Degree' in i]

        for part in self._post_config.instruments_to_keep:
            join_part_degrees(total_degrees, get_part_prefix(part), self.data)
        join_part_degrees(total_degrees, get_sound_prefix('voice'), self.data)
        # self.data.drop(total_degrees, axis = 1, inplace=True)
    
    def _scan_dataframe(self):
        self.composer_counter = []
        self.novoices_counter = []

        for i, comp in enumerate(self.data[COMPOSER].values):
            if pd.isnull(comp):
                self.composer_counter.append(self.data[FILE_NAME][i])
                self.data.drop(i, axis = 0, inplace=True)

        for i, voice in enumerate(self.data[VOICES].values):
            if pd.isnull(voice):
                self.novoices_counter.append(self.data[FILE_NAME][i])
                self.data.drop(i, axis = 0, inplace=True)

    def _final_data_processing(self) -> None:
        self.data.sort_values(ARIA_ID, inplace=True)
        replace_nans(self.data)
        log_errors_and_shape(self.composer_counter, self.novoices_counter, self.data)
        self.data = self.data.reindex(sorted(self.data.columns), axis=1)
        columns_to_sort=columns_order+list(self.data.filter(like='Label_', axis=1))
        self.data = sort_columns(self.data, columns_to_sort)
        self.data.drop('index', axis = 1, inplace=True, errors='ignore')
        dest_path=self.destination_route + "_processed" + ".csv"
        self.to_csv(dest_path)



