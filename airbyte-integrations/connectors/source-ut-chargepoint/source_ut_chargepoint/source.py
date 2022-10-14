#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#


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
                    for _resp in getattr(response, self.field_pointer):
                        resp = zeep.helpers.serialize_object(_resp, dict)
                        yield resp

                    more = response.MoreFlag

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

        if cursor_field[0] not in stream_state:
            stream_state[cursor_field[0]] = 1

        session_search_query = {'startRecord': stream_state[cursor_field[0]]}

        try:
            client_function = getattr(self.client.service, self.endpoint)

            more = True
            while more:
                response = client_function(session_search_query)

                if response.responseCode == '100':
                    for _resp in getattr(response, self.field_pointer):
                        resp = zeep.helpers.serialize_object(_resp, dict)
                        yield resp
                        self.state = resp

                    session_search_query.update({'startRecord': self.state[cursor_field[0]]})
                    more = response.MoreFlag

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


# Source
class SourceUtChargepoint(AbstractSource):
    def check_connection(self, logger, config) -> Tuple[bool, any]:
        """
        TODO: Implement a connection check to validate that the user-provided config can be used to connect to the underlying API

        See https://github.com/airbytehq/airbyte/blob/master/airbyte-integrations/connectors/source-stripe/source_stripe/source.py#L232
        for an example.

        :param config:  the user-input config object conforming to the connector's spec.yaml
        :param logger:  logger object
        :return Tuple[bool, any]: (True, None) if the input config can be used to connect to the API successfully, (False, error) otherwise.
        """
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
        """
        TODO: Replace the streams below with your own streams.

        :param config: A Mapping of the user input configuration as defined in the connector spec.
        """
        return[GetChargingSessionData(config=config), GetStations(config=config)]
