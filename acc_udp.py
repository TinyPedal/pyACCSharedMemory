"""
Python mapping of ACC's Broadcasting Network Protocol (UDP)

Based on ACC Broadcasting SDK, found in game's "sdk\\broadcasting" folder.
"""

from __future__ import annotations

import ctypes
import io
import logging
import socket
import struct
from contextlib import contextmanager
from time import perf_counter
from typing import Callable, Sequence

from ._common import _t, get_root_logger_name, typedstruct

logger = logging.getLogger(get_root_logger_name())


# Constants
class OutboundMessageTypes:
    """Outbound message types"""

    REGISTER_COMMAND_APPLICATION = 1
    UNREGISTER_COMMAND_APPLICATION = 9
    REQUEST_ENTRY_LIST = 10
    REQUEST_TRACK_DATA = 11
    CHANGE_HUD_PAGE = 49
    CHANGE_FOCUS = 50
    INSTANT_REPLAY_REQUEST = 51
    PLAY_MANUAL_REPLAY_HIGHLIGHT = 52
    SAVE_MANUAL_REPLAY_HIGHLIGHT = 60


class InboundMessageTypes:
    """Inbound message types"""

    REGISTRATION_RESULT = 1
    REALTIME_UPDATE = 2
    REALTIME_CAR_UPDATE = 3
    ENTRY_LIST = 4
    ENTRY_LIST_CAR = 6
    TRACK_DATA = 5
    BROADCASTING_EVENT = 7


class BroadcastingNetworkProtocol:
    """Broadcasting network protocol"""

    BROADCASTING_PROTOCOL_VERSION = 4
    BUFFER_SIZE = 4096  # 2 ** 14
    MAX_MAPPED_VEHICLES: int = 60
    MAX_LINE_UP: int = 10


# UDP API data
@typedstruct(pack=4)
class UDPDriverInfo(ctypes.Structure):
    """Driver info

    Attributes:
        firstName: first name
        lastName: last name
        shortName: short name
        category: Platinum = 3, Gold = 2, Silver = 1, Bronze = 0
        nationality: nationality, see NationalityEnum enum
    """

    __slots__ = ()

    firstName: bytes = _t(ctypes.c_char * 32)
    lastName: bytes = _t(ctypes.c_char * 32)
    shortName: bytes = _t(ctypes.c_char * 32)
    category: int = _t(ctypes.c_byte)
    nationality: int = _t(ctypes.c_int16)


@typedstruct(pack=4)
class UDPLapInfo(ctypes.Structure):
    """Lap info

    Attributes:
        laptimeMS: lap time in milliseconds
        carIndex: car index
        driverIndex: driver index
        splitCount: number of lap time records
        isInvalid: is invalid lap time
        isValidForBest: is valid for best lap time
        isOutlap: is out lap
        isInlap: is in lap
        lapType: lap type, see LapType enum
    """

    __slots__ = ()

    laptimeMS: int = _t(ctypes.c_int32)
    carIndex: int = _t(ctypes.c_int16)
    driverIndex: int = _t(ctypes.c_int16)
    splitCount: int = _t(ctypes.c_byte)
    # splits: list[int] = _t(ctypes.c_int32 * 1000)  # (unmapped) list of lap time records
    isInvalid: bool = _t(ctypes.c_bool)
    isValidForBest: bool = _t(ctypes.c_bool)
    isOutlap: bool = _t(ctypes.c_bool)
    isInlap: bool = _t(ctypes.c_bool)
    lapType: int = _t(ctypes.c_byte)


@typedstruct(pack=4)
class UDPCarInfo(ctypes.Structure):
    """Car info

    Attributes:
        entryIndex: car index from ENTRY_LIST_CAR
        carIndex: car index from REALTIME_CAR_UPDATE
        carModelType: car model type
        teamName: team name
        raceNumber: race number
        cupCategory: Cup: Overall/Pro = 0, ProAm = 1, Am = 2, Silver = 3, National = 4, see CupCategory enum
        currentDriverIndex: current driver index
        currentDriverInfo: current driver info from this car (team)
        driverCount: number of drivers in team for this car (shared with REALTIME_CAR_UPDATE)
        nationality: nationality
        driverIndex: who is driving in team, driver swap will make this change
        gear: -1=reverse, 0=neutral, 1+=forward
        worldPosX: world position X
        worldPosY: world position Y
        yaw: yaw angle in radians (slow)
        carLocation: 0=None, 1=Track, 2=Pitlane, 3=PitEntry, 4=PitExit, see CarLocation enum
        speedKmh: speed in kilometers per hour
        position: official P/Q/R position (1 based)
        cupPosition: official P/Q/R position (1 based)
        trackPosition: position on track (1 based)
        splinePosition: track position between 0.0 and 1.0
        completedLaps: number of completed laps
        deltaBest: realtime delta to best session lap
        bestSessionLap: session best lap data
        lastLap: last lap time data
        currentLap: current lap time data
    """

    __slots__ = ()

    entryIndex: int = _t(ctypes.c_int16)
    carIndex: int = _t(ctypes.c_int16)
    carModelType: int = _t(ctypes.c_byte)
    teamName: bytes = _t(ctypes.c_char * 64)
    raceNumber: int = _t(ctypes.c_int32)
    cupCategory: int = _t(ctypes.c_byte)
    currentDriverIndex: int = _t(ctypes.c_byte)
    currentDriverInfo: UDPDriverInfo = _t(UDPDriverInfo)
    driverCount: int = _t(ctypes.c_byte)
    #drivers: list of driver info from this car (team)
    #drivers: list[UDPDriverInfo] = _t(UDPDriverInfo * BroadcastingNetworkProtocol.MAX_LINE_UP)
    nationality: int = _t(ctypes.c_int16)
    # REALTIME_CAR_UPDATE = 3
    driverIndex: int = _t(ctypes.c_int16)
    gear: int = _t(ctypes.c_byte)
    worldPosX: float = _t(ctypes.c_float)
    worldPosY: float = _t(ctypes.c_float)
    yaw: float = _t(ctypes.c_float)
    carLocation: int = _t(ctypes.c_byte)
    speedKmh: int = _t(ctypes.c_int16)
    position: int = _t(ctypes.c_int16)
    cupPosition: int = _t(ctypes.c_int16)
    trackPosition: int = _t(ctypes.c_int16)
    splinePosition: float = _t(ctypes.c_float)
    completedLaps: int = _t(ctypes.c_int16)
    deltaBest: int = _t(ctypes.c_int32)
    bestSessionLap: UDPLapInfo = _t(UDPLapInfo)
    lastLap: UDPLapInfo = _t(UDPLapInfo)
    currentLap: UDPLapInfo = _t(UDPLapInfo)


@typedstruct(pack=4)
class UDPTrackData(ctypes.Structure):
    """TRACK_DATA = 5

    Attributes:
        connectionId: connection ID
        trackName: track name
        trackId: track ID
        trackMeters: track length in meters
    """

    __slots__ = ()

    connectionId: int = _t(ctypes.c_int)
    trackName: bytes = _t(ctypes.c_char * 64)
    trackId: int = _t(ctypes.c_byte)
    trackMeters: int = _t(ctypes.c_float)
    # (unmapped) CameraSets
    # (unmapped) HUDPages


@typedstruct(pack=4)
class UDPRegistrationResult(ctypes.Structure):
    """REGISTRATION_RESULT = 1

    Attributes:
        connectionId: connection ID
        connectionSuccess: whether connection success
        host: UDP host name
        port: UDP port number
        isReadOnly: is read only connection
        errorMessage: error message
    """

    __slots__ = ()

    connectionId: int = _t(ctypes.c_int)
    connectionSuccess: bool = _t(ctypes.c_bool)
    hostUDP: str = _t(ctypes.c_wchar * 32)
    portUDP: int = _t(ctypes.c_int)
    isReadOnly: bool = _t(ctypes.c_bool)
    errorMessage: bytes = _t(ctypes.c_char * 64)


@typedstruct(pack=4)
class UDPEntryList(ctypes.Structure):
    """ENTRY_LIST = 4, ENTRY_LIST_CAR = 6

    Attributes:
        connectionId: connection ID
        carEntryCount: car entry count
        entryListCars: entry list cars
        lastEntrylistRequest: last entry list request
        syncEntryList: whether to sync entry list
    """

    __slots__ = ()

    connectionId: int = _t(ctypes.c_int32)
    carEntryCount: int = _t(ctypes.c_int16)
    entryListCars: list[UDPCarInfo] = _t(UDPCarInfo * BroadcastingNetworkProtocol.MAX_MAPPED_VEHICLES)
    lastEntrylistRequest: float = _t(ctypes.c_double)
    syncEntryList: bool = _t(ctypes.c_bool)


@typedstruct(pack=4)
class UDPSessionInfo(ctypes.Structure):
    """REALTIME_UPDATE = 2

    Attributes:
        eventIndex: event index, see BroadcastingCarEventType enum
        sessionIndex: session index
        sessionType: session type, see RaceSessionType enum
        sessionPhase: session phase, see SessionPhase enum
        sessionTime: session time
        sessionEndTime: session end time
        focusedCarIndex: focused car index
        activeCameraSet: active camera set name
        activeCamera: active camera name
        currentHudPage: current hud page
        isReplayPlaying: is replay playing
        replaySessionTime: replay session time
        replayRemainingTime: replay remaining time
        timeOfDay: time of day
        ambientTemp: ambient temperature
        trackTemp: track temperature
        clouds: clouds
        rainLevel: rain level
        wetness: track wetness
        bestSessionLap: session best lap data
    """

    __slots__ = ()

    eventIndex: int = _t(ctypes.c_int16)
    sessionIndex: int = _t(ctypes.c_int16)
    sessionType: int = _t(ctypes.c_byte)
    sessionPhase: int = _t(ctypes.c_byte)
    sessionTime: float = _t(ctypes.c_float)
    sessionEndTime: float = _t(ctypes.c_float)
    focusedCarIndex: int = _t(ctypes.c_int32)
    activeCameraSet: bytes = _t(ctypes.c_char * 32)
    activeCamera: bytes = _t(ctypes.c_char * 32)
    currentHudPage: bytes = _t(ctypes.c_char * 32)
    isReplayPlaying: bool = _t(ctypes.c_bool)
    replaySessionTime: float = _t(ctypes.c_float)
    replayRemainingTime: float = _t(ctypes.c_float)
    timeOfDay: float = _t(ctypes.c_float)
    ambientTemp: int = _t(ctypes.c_byte)
    trackTemp: int = _t(ctypes.c_byte)
    clouds: float = _t(ctypes.c_float)
    rainLevel: float = _t(ctypes.c_float)
    wetness: float = _t(ctypes.c_float)
    bestSessionLap: UDPLapInfo = _t(UDPLapInfo)


@typedstruct(pack=4)
class UDPBroadcastOutput(ctypes.Structure):
    """Broadcast data output

    Attributes:
        registration: registration result info
        sessionInfo: session info
        entryList: car entry list
        trackData: track data
    """

    __slots__ = ()

    registration: UDPRegistrationResult = _t(UDPRegistrationResult)
    sessionInfo: UDPSessionInfo = _t(UDPSessionInfo)
    entryList: UDPEntryList = _t(UDPEntryList)
    trackData: UDPTrackData = _t(UDPTrackData)

    def __del__(self):
        logger.info("UDP: GC: UDPBroadcastOutput")

    @classmethod
    def size(cls) -> int:
        """Return data structure size"""
        return ctypes.sizeof(cls)


# Function
bytes_to_int = lambda bytes: int.from_bytes(bytes, "little")
bytes_to_float = lambda bytes: struct.unpack("<f", bytes)[0]


def write_string(string: str, data: bytearray):
    """Write string to data bytes"""
    bytestring = string.encode()
    data.extend(len(bytestring).to_bytes(2, "little"))
    data.extend(bytestring)


def read_string(stream: io.BytesIO, size: int) -> bytes:
    """Read string to data bytes"""
    return stream.read(bytes_to_int(stream.read(size)))


# Set message
def set_register_message(
    display_name: str = "",
    connection_password: str = "",
    command_password: str = "",
    realtime_update_interval: int = 250,
    register_command_application: int = OutboundMessageTypes.REGISTER_COMMAND_APPLICATION,
    broadcasting_protocol_version: int = BroadcastingNetworkProtocol.BROADCASTING_PROTOCOL_VERSION,
) -> bytearray:
    """Set message for registering connection for current client

    Args:
        display_name: display name (optional).
        connection_password: connection password (optional) matches broadcasting.json 'connectionPassword' value; wrong password will result connection failure.
        command_password: command password (optional) matches broadcasting.json 'command_password' value; wrong password will grant read-only access.
        realtime_update_interval: UDP data realtime update interval (milliseconds).
    """
    message = bytearray()
    message.extend(register_command_application.to_bytes(1, "little"))
    message.extend(broadcasting_protocol_version.to_bytes(1, "little"))
    write_string(display_name, message)
    write_string(connection_password, message)
    message.extend(int(max(realtime_update_interval, 10)).to_bytes(4, "little"))
    write_string(command_password, message)
    return message


def set_message(message_type: int, connection_id: int) -> bytes:
    """Set message: message type, connection id"""
    return struct.pack("<bi", message_type, connection_id)


# Read stream
def read_registration_result(stream: io.BytesIO, output: UDPRegistrationResult):
    """Read stream - registration result"""
    output.connectionId = bytes_to_int(stream.read(4))  # Int32
    output.connectionSuccess = bytes_to_int(stream.read(1)) > 0  # byte
    output.isReadOnly = bytes_to_int(stream.read(1)) == 0  # byte
    output.errorMessage = read_string(stream, 2)[:64]  # bytestring


def read_lap_info(stream: io.BytesIO, output: UDPLapInfo):
    """Read stream - lap info"""
    output.laptimeMS = bytes_to_int(stream.read(4))  # Int32
    output.carIndex = bytes_to_int(stream.read(2))  # UInt16
    output.driverIndex = bytes_to_int(stream.read(2))  # UInt16
    output.splitCount = bytes_to_int(stream.read(1))  # byte
    stream.seek(output.splitCount * 4, 1)  # skip lap history (save memory)
    #for i in range(min(output.splitCount, 1000)):
    #    output.splits[i] = bytes_to_int(stream.read(4))  # list Int32
    output.isInvalid = bytes_to_int(stream.read(1)) > 0  # bool
    output.isValidForBest = bytes_to_int(stream.read(1)) > 0  # bool
    output.isOutlap = bytes_to_int(stream.read(1)) > 0  # bool
    output.isInlap = bytes_to_int(stream.read(1)) > 0  # bool
    if output.isOutlap:
        output.lapType = 1
    elif output.isInlap:
        output.lapType = 3
    else:
        output.lapType = 2


def read_realtime_update(stream: io.BytesIO, output: UDPSessionInfo):
    """Read stream - realtime update"""
    output.eventIndex = bytes_to_int(stream.read(2))  # UInt16
    output.sessionIndex = bytes_to_int(stream.read(2))  # UInt16
    output.sessionType = bytes_to_int(stream.read(1))  # byte
    output.sessionPhase = bytes_to_int(stream.read(1))  # byte
    output.sessionTime = bytes_to_float(stream.read(4))  # float
    output.sessionEndTime = bytes_to_float(stream.read(4))  # float
    output.focusedCarIndex = bytes_to_int(stream.read(4))  # Int32
    output.activeCameraSet = read_string(stream, 2)  # bytestring
    output.activeCamera = read_string(stream, 2)  # bytestring
    output.currentHudPage = read_string(stream, 2)  # bytestring
    output.isReplayPlaying = bytes_to_int(stream.read(1)) > 0  # byte
    if output.isReplayPlaying:
        output.replaySessionTime = bytes_to_float(stream.read(4))  # float
        output.replayRemainingTime = bytes_to_float(stream.read(4))  # float
    output.timeOfDay = bytes_to_float(stream.read(4))  # float
    output.ambientTemp = bytes_to_int(stream.read(1))  # byte
    output.trackTemp = bytes_to_int(stream.read(1))  # byte
    output.clouds = bytes_to_int(stream.read(1)) / 10.0  # byte to float
    output.rainLevel = bytes_to_int(stream.read(1)) / 10.0  # byte to float
    output.wetness = bytes_to_int(stream.read(1)) / 10.0  # byte to float
    read_lap_info(stream, output.bestSessionLap)


def read_realtime_car_update(
    stream: io.BytesIO,
    output: UDPEntryList,
    max_vehicles: int = BroadcastingNetworkProtocol.MAX_MAPPED_VEHICLES,
):
    """Read stream - realtime car update"""
    car_id = bytes_to_int(stream.read(2))  # UInt16
    driver_index = bytes_to_int(stream.read(2))  # UInt16
    driver_count = bytes_to_int(stream.read(1))  # byte
    if car_id >= max_vehicles:
        return
    car_info = output.entryListCars[car_id]
    # Check if entry list outdated
    if car_info.entryIndex != car_id or car_info.driverCount != driver_count:
        current_timestamp = perf_counter()
        if current_timestamp - output.lastEntrylistRequest > 1:
            output.lastEntrylistRequest = current_timestamp
            output.syncEntryList = True
    # Update realtime car info
    car_info.carIndex = car_id
    car_info.driverIndex = driver_index
    car_info.driverCount = driver_count
    car_info.gear = bytes_to_int(stream.read(1)) - 2  # byte
    car_info.worldPosX = bytes_to_float(stream.read(4))  # float
    car_info.worldPosY = bytes_to_float(stream.read(4))  # float
    car_info.yaw = bytes_to_float(stream.read(4))  # float
    car_info.carLocation = bytes_to_int(stream.read(1))  # byte
    car_info.speedKmh = bytes_to_int(stream.read(2))  # UInt16
    car_info.position = bytes_to_int(stream.read(2))  # UInt16
    car_info.cupPosition = bytes_to_int(stream.read(2))  # UInt16
    car_info.trackPosition = bytes_to_int(stream.read(2))  # UInt16
    car_info.splinePosition = bytes_to_float(stream.read(4))  # float
    car_info.completedLaps = bytes_to_int(stream.read(2))  # UInt16
    car_info.deltaBest = bytes_to_int(stream.read(4))  # Int32
    read_lap_info(stream, car_info.bestSessionLap)
    read_lap_info(stream, car_info.lastLap)
    read_lap_info(stream, car_info.currentLap)


def read_entry_list(stream: io.BytesIO, output: UDPEntryList):
    """Read stream - entry list"""
    output.connectionId = bytes_to_int(stream.read(4))  # Int32
    output.carEntryCount = bytes_to_int(stream.read(2))  # UInt16


def read_entry_list_car(
    stream: io.BytesIO,
    output: UDPEntryList,
    max_vehicles: int = BroadcastingNetworkProtocol.MAX_MAPPED_VEHICLES,
    max_lineup: int = BroadcastingNetworkProtocol.MAX_LINE_UP,
):
    """Read stream - entry list car info"""
    car_id = bytes_to_int(stream.read(2))  # UInt16
    if car_id >= max_vehicles:
        return
    car_info = output.entryListCars[car_id]
    car_info.entryIndex = car_id
    car_info.carModelType = bytes_to_int(stream.read(1))  # byte
    car_info.teamName = read_string(stream, 2)  # bytestring
    car_info.raceNumber = bytes_to_int(stream.read(4))  # Int32
    car_info.cupCategory = bytes_to_int(stream.read(1))  # byte
    car_info.currentDriverIndex = bytes_to_int(stream.read(1))  # byte
    car_info.nationality = bytes_to_int(stream.read(2))  # UInt16
    car_info.driverCount = bytes_to_int(stream.read(1))  # byte
    for i in range(min(car_info.driverCount, max_lineup)):
        first_name = read_string(stream, 2)  # bytestring
        last_name = read_string(stream, 2)  # bytestring
        short_name = read_string(stream, 2)  # bytestring
        category = bytes_to_int(stream.read(1))  # byte
        nationality = bytes_to_int(stream.read(2))  # UInt16
        if car_info.driverIndex == i:
            current_driver = car_info.currentDriverInfo
            current_driver.firstName = first_name
            current_driver.lastName = last_name
            current_driver.shortName = short_name
            current_driver.category = category
            current_driver.nationality = nationality
            return


def read_track_data(stream: io.BytesIO, output: UDPTrackData):
    """Read stream - track data"""
    output.connectionId = bytes_to_int(stream.read(4))  # Int32
    output.trackName = read_string(stream, 2)  # bytestring
    output.trackId = bytes_to_int(stream.read(4))  # Int32
    output.trackMeters = bytes_to_int(stream.read(4))  # Int32


# Parse data
def parse_udp_stream(response: bytes, output: UDPBroadcastOutput) -> int:
    """Parse ACC UDP data stream"""
    if not response:
        return -1
    data_stream = io.BytesIO(response)
    message_type = bytes_to_int(data_stream.read(1))
    # Ordered by most frequent accessed message type
    if message_type == 3:  # InboundMessageTypes.REALTIME_CAR_UPDATE
        read_realtime_car_update(data_stream, output.entryList)
    elif message_type == 2:  # InboundMessageTypes.REALTIME_UPDATE
        read_realtime_update(data_stream, output.sessionInfo)
    elif message_type == 6:  # InboundMessageTypes.ENTRY_LIST_CAR
        read_entry_list_car(data_stream, output.entryList)
    elif message_type == 4:  # InboundMessageTypes.ENTRY_LIST
        read_entry_list(data_stream, output.entryList)
    elif message_type == 5:  # InboundMessageTypes.TRACK_DATA
        read_track_data(data_stream, output.trackData)
    elif message_type == 1:  # InboundMessageTypes.REGISTRATION_RESULT
        read_registration_result(data_stream, output.registration)
    data_stream.close()
    return message_type


# UDP connection function
@contextmanager
def acc_udp_connect(
    udp_host: str,
    udp_port: int,
    udp_output: UDPBroadcastOutput,
    connection_message: bytes | bytearray = b"",
    connection_timeout: float = 1.0,
    callback_function: Callable[[int], None] | None = None,
):
    """Connect client to ACC UDP API

    Args:
        udp_host: UDP host name.
        udp_port: UDP port matches broadcasting.json 'updListenerPort' value.
        udp_output: UDP broadcast output data.
        connection_message: set register connection message, see 'set_register_message' function.
        connection_timeout: UDP connection timeout (seconds).
    """
    udp_output.registration.hostUDP = udp_host
    udp_output.registration.portUDP = udp_port
    server_address = (udp_host, udp_port)
    connection_id = -999
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(connection_timeout)
    try:
        # Send register message
        logger.info("UDP: REQUESTED: REGISTER_COMMAND_APPLICATION")
        sock.sendto(connection_message, server_address)

        # Get response
        response, _ = sock.recvfrom(128)
        parse_udp_stream(response, udp_output)

        # Update connection id
        connection_id = udp_output.registration.connectionId
        error_message = udp_output.registration.errorMessage

        # Failed (usually due to wrong connection password)
        if not udp_output.registration.connectionSuccess:
            logger.error("UDP: ERROR: %s", error_message.decode())
            raise OSError

        # Connection info
        logger.info("UDP: CONNECTED: ACC Broadcasting Protocol (v%s)", BroadcastingNetworkProtocol.BROADCASTING_PROTOCOL_VERSION)
        logger.info("UDP: CLIENT: #%s (%s:%s)", connection_id, udp_host, udp_port)
        if udp_output.registration.errorMessage:
            logger.info("UDP: CLIENT: %s", error_message.decode())
        yield sock

    finally:
        # Disconnect current client & close socket
        if connection_id != -999:
            logger.info("UDP: REQUESTED: UNREGISTER_COMMAND_APPLICATION")
            sock.sendto(set_message(OutboundMessageTypes.UNREGISTER_COMMAND_APPLICATION, connection_id), server_address)
            logger.info("UDP: DISCONNECTING: ACC Broadcasting Protocol (v%s)", BroadcastingNetworkProtocol.BROADCASTING_PROTOCOL_VERSION)
            logger.info("UDP: DISCONNECTED: CLIENT: #%s (%s:%s)", connection_id, udp_host, udp_port)
        sock.close()
        # Run callback function
        if callable(callback_function):
            callback_function(connection_id)


def acc_udp_disconnect(
    udp_host: str,
    udp_port: int,
    connection_id: Sequence[int],
    connection_timeout: float = 1.0,
):
    """Unregister & disconnect specific list of clients from ACC UDP API

    Args:
        udp_host: UDP host name.
        udp_port: UDP port matches broadcasting.json 'updListenerPort' value.
        connection_id: disconnect all clients from connection ID list.
        connection_timeout: UDP connection timeout (seconds).
    """
    if not connection_id:
        return
    server_address = (udp_host, udp_port)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(connection_timeout)
        # Disconnect all clients, 9=OutboundMessageTypes.UNREGISTER_COMMAND_APPLICATION
        logger.info("UDP: REQUESTED: UNREGISTER_COMMAND_APPLICATION")
        for client_id in set(connection_id):
            sock.sendto(set_message(9, client_id), server_address)
            logger.info("UDP: PURGED CLIENT: #%s (%s:%s)", client_id, udp_host, udp_port)
