import os, csv, json
from abc import ABC
import datetime as dt
import pandas as pd
from typing import Self, Any, Optional
import QuantLib as ql
from fixedincomelib.date import Date, Period
from fixedincomelib.date.basics import TermOrTerminationDate
from fixedincomelib.utilities import Registry, get_config
from fixedincomelib.market.data_conventions import DataConventionRegistry

######################################### REGISTRY #########################################

class IndexRegistry(Registry):
    
    def __new__(cls) -> Self:
        return super().__new__(cls, 'indices', 'Index')

    def register(self, key : Any, value : Any) -> None:
        super().register(key, value)
        # delegate index to ql
        ql_object = None
        try:
            ql_object = getattr(ql, value)
        except AttributeError:
            raise KeyError(f"QuantLib has no attribute '{value}' for key '{key}'")
        try:
            # if this is not an termed index
            self._map[key.upper()] = ql_object()
        except:
            err_msg = f'Cannot create a term index for key {key}.'
            tenor = str(key).split('-')[-1]
            if not TermOrTerminationDate(tenor).is_term():
                raise Exception(err_msg)
            self._map[key] = ql_object(Period(tenor))

    def get(self, key: Any, **args) -> Any:
        if key.upper() not in self._map:
            raise Exception(f'Cannot find {key} in index registry.')
        return self._map[key.upper()]

    def display_all_indices(self) -> pd.DataFrame:
        to_print = []
        for k, _ in self._map.items():
            index : ql.QuantLib.Index = self.get(k)
            index_name = index.name()
            to_print.append([k, index_name])
        return pd.DataFrame(to_print, columns=['Name', 'QuantLibIndex'])
    
    @classmethod
    def look_up_index_name(cls, index : ql.Index):
        for k, v in cls._instance._map.items():
            if index.name() == v.name():
                return k
        raise Exception(f'Cannot find index name for {index.name()}.')

class IndexFixingsManager(Registry):

    _fixing_path = None

    def __new__(cls) -> Self:
        if cls._fixing_path is None:
            this_config = get_config()
            cls._fixing_path = this_config['FIXING_SOURCE']
        return super().__new__(cls, 'fixings', 'IndexFixings')
    
    def register(self, key : Any, value : Any) -> None:
        super().register(key, value)
        this_path = os.path.join(self._fixing_path, f'{key.lower()}.csv')
        if os.path.exists(this_path):
            with open(this_path, newline='') as csv_file:
                csv_reader = csv.DictReader(csv_file)
                for this_line in csv_reader:
                    fixing_date = Date(dt.datetime.strptime(this_line['date'], '%Y-%m-%d').date())
                    self._map.setdefault(key.upper(), {})[fixing_date] = float(this_line["fixing"])
    
    def insert_fixing(self, index : str, date : Date, fixing : float):
        this_map = self.get(index.lower())
        if date in this_map:
            return
        else:
            this_map[date] = fixing

    def exist_fixing(self, index : str, date : Date):
        this_map = self.get(index.lower())
        return date in this_map

    def get_fixing(self, index : str, date : Date):
        this_map = self.get(index.lower())
        if date in this_map:
            return this_map[date]
        else:
            raise Exception(f'Cannot find {index} for date {date.ISO()}')
        
    def remove_fixing(self, index : str, date : Optional[Date]=None):
        if date is None:
            self.erase(index)
        else:
            this_map : dict = self.get(index)
            this_map.pop(Date(date))


class DataIdentifierRegistry(Registry):

    def __new__(cls) -> Self:
        return super().__new__(cls, '', cls.__name__)

    def register(self, key : Any, value : Any) -> None:
        super().register(key, value)
        self._map[key] = value


############################################################################################



