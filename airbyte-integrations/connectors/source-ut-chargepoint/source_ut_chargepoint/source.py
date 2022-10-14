#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#

from distutils.command.config import config
from typing import  Mapping, Tuple, Any, List, Iterable

from abc import ABC, abstractmethod
import zeep
from zeep.wsse.username import UsernameToken

from airbyte_cdk.logger import AirbyteLogger
from airbyte_cdk.models import (
    AirbyteMessage,
    AirbyteLogMessage,
    Level,
    SyncMode,
    Type,
)
from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream, IncrementalMixin


class BaseChargepointStream(Stream, ABC):

    def __init__(self, config):
        self.client = zeep.Client(
            config['wsdl'],
            wsse=UsernameToken(config['username'], config['password'])
        )

    @property
    @abstractmethod
    def field_pointer(self) -> str:
        """The response field containing the records"""
        ...

    @property
    @abstractmethod
    def endpoint(self) -> str:
        """The Api endpoing"""
        ...


class FullRefreshChargepointStream(BaseChargepointStream):

    def __init__(self, config):
        super().__init__(config)

    def read_records(
        self,
        sync_mode: SyncMode,
        cursor_field: List[str] = None,
        stream_slice: Mapping[str, Any] = None,
        stream_state: Mapping[str, Any] = None,
    ) -> Iterable[Mapping[str, Any]]:

        try:
            client_function = getattr(self.client.service, self.endpoint)
            more = True
            while more:
                response = client_function({})
                if response.responseCode == '100':
                    for resp in getattr(response, self.field_pointer):
                        yield resp

                    more = response.moreFlag

                else:
                    self.logger.error(response.responseText)
                    more = False
                    yield []

        except Exception as e:
            yield AirbyteMessage(
                type=Type.LOG,
                log=AirbyteLogMessage(
                    level=Level.FATAL,
                    message=f"Exception occured while reading data from {self.name}. {str(e)}"
                )
            )


class IncrementalChargepointStream(BaseChargepointStream, IncrementalMixin):

    def __init__(self, config):
        super().__init__(config)

    def read_records(
        self,
        sync_mode: SyncMode,
        cursor_field: List[str] = None,
        stream_slice: Mapping[str, Any] = None,
        stream_state: Mapping[str, Any] = None,
    ) -> Iterable[Mapping[str, Any]]:

        if cursor_field not in stream_state:
            stream_state[cursor_field] = 1

        session_search_query = {'startRecord': stream_state[cursor_field]}

        try:
            client_function = getattr(self.client.service, self.endpoint)

            more = True
            while more:
                response = client_function(session_search_query)

                if response.responseCode == '100':
                    for resp in getattr(response, self.field_pointer):
                        yield resp
                        self.state = resp

                    more = response.moreFlag

                else:
                    self.logger.error(response.responseText)
                    more = False
                    yield []

        except Exception as e:
            yield AirbyteMessage(
                type=Type.LOG,
                log=AirbyteLogMessage(
                    level=Level.FATAL,
                    message=f"Exception occured while reading data from {self.name}. {str(e)}"
                )
            )


    @property
    @abstractmethod
    def start_record(self) -> int:
        ...

    @property
    def state(self):
        return {self.cursor_field: str(self._cursor_value)} if self._cursor_value else {}

    @state.setter
    def state(self, value):
        self._cursor_value = value.get(self.cursor_field, self.start_record)


class GetChargingSessionData(IncrementalChargepointStream):

    cursor_field = 'recordNumber'
    field_pointer = 'ChargingSessionData'
    primary_key = ['sessionID']
    state_checkpoint_interval = 100
    start_record = 1
    endpoint = 'getChargingSessionData'


class GetStations(FullRefreshChargepointStream):

    field_pointer = 'stationData'
    primary_key = ['stationID', 'stationSerialNum', 'sgID']
    endpoint = 'getStations'


class SourceUtChargepoint(AbstractSource):
    def check_connection(self, logger: AirbyteLogger, config: Mapping[str, Any]) -> Tuple[bool, Any]:
        try:
            client = zeep.Client(
                config['wsdl'],
                wsse=UsernameToken(config['username'], config['password'])
            )
            sample = client.service.getStations({})
            if sample.responseCode == '100':
                return True, None
            return False, sample.response_text
        except Exception as e:
            return False, repr(e)

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        return[GetChargingSessionData(config=config), GetStations(config=config)]
