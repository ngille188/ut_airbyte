#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#


import json
from datetime import datetime
from logging import _Level
from typing import Dict, Generator, Mapping, Tuple, Any, List, Iterable

import zeep
from zeep import helpers
from zeep.wsse.username import UsernameToken

from airbyte_cdk.logger import AirbyteLogger
from airbyte_cdk.models import (
    AirbyteCatalog,
    AirbyteConnectionStatus,
    AirbyteMessage,
    AirbyteLogMessage,
    AirbyteRecordMessage,
    AirbyteStream,
    ConfiguredAirbyteCatalog,
    Status,
    Level,
    SyncMode,
    Type,
)
from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream, IncrementalMixin

class FullRefreshChargePointStream(Stream):

    def __init__(self, config: Mapping[str, Any]):
        self.config = config


    @property
    def field_pointer(self) -> str:
        """The response field containing the records"""
        pass

    @property
    def endpoint(self) -> str:
        pass

    def read_records(
        self,
        sync_mode: SyncMode,
        cursor_field: List[str] = None,
        stream_slice: Mapping[str, Any] = None,
        stream_state: Mapping[str, Any] = None,
    ) -> Iterable[Mapping[str, Any]]:

        client = zeep.Client(
            self.config['wsdl'],
            wsse=UsernameToken(self.config['username'], self.config['password'])
        )
        try:
            client_function = getattr(client.service, self.endpoint)
            response = client_function({})

            if response.response_code == '100':
                for resp in getattr(response, self.field_pointer):
                    yield resp

            else:
                self.logger.error(response.response_text)
                yield []
        except Exception as e:
            yield AirbyteMessage(
                type=Type.LOG,
                log=AirbyteLogMessage(
                    level=Level.FATAL,
                    message=f"Exception occured while reading data from {self.name}. {str(e)}"
                )
            )


class IncrementalChargePointStream(Stream, IncrementalMixin):

    def __init__(self, config: Mapping[str, Any]):
        self.config = config


    def read_records(
        self,
        sync_mode: SyncMode,
        cursor_field: List[str] = None,
        stream_slice: Mapping[str, Any] = None,
        stream_state: Mapping[str, Any] = None,
    ) -> Iterable[Mapping[str, Any]]:

       pass


    @property
    def cursor_field(self) -> str:
        """
        Defining a cursor field indicates that a stream is incremental, so any incremental stream must extend this class
        and define a cursor field.
        """
        pass

    @property
    def field_pointer(self) -> str:
        """The response field containing the records"""
        pass

    @property
    def endpoint(self) -> str:
        pass

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        self._state[self.cursor_field] = value[self.cursor_field]


class GetChargingSessionData(IncrementalChargePointStream):
    '''
    Properties to be implemented:
        cursor_field
        field_pointer
        primary key: return None if there isn't a primary key
        state_interval_checkpoint
    '''
    cursor_field = 'recordNumber'
    field_pointer = 'ChargingSessionData'
    primary_key = ['sessionID']
    state_checkpoint_interval = 100


class GetStations(FullRefreshChargePointStream):
    '''
    Properties to be implemented:
        cursor_field
        field_pointer
        primary key: return None if there isn't a primary key

    '''
    field_pointer = 'stationData'
    primary_key = ['stationID', 'stationSerialNum', 'sgID']





class SourceChargePoint(AbstractSource):
    def check_connection(self, logger: AirbyteLogger, config: Mapping[str, Any]) -> Tuple[bool, Any]:
        try:
            zeep.Client(
                config['url'],
                wsse=UsernameToken(config['username'], config['password'])
            )
            return True, None
        except Exception as e:
            return False, repr(e)

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        return[GetChargingSessionData(config=config), GetStations(config=config)]
