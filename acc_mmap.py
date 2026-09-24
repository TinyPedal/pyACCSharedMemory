"""
ACC Memory Map Control for accessing ACC Shared Memory Interface
"""

from __future__ import annotations

import ctypes
import logging
import mmap
import platform

from ._common import get_root_logger_name
from .acc_data import ACCConstants

logger = logging.getLogger(get_root_logger_name())


def platform_mmap(name: str, size: int) -> mmap.mmap:
    """Platform memory mapping"""
    if platform.system() == "Windows":
        return windows_mmap(name, size)
    return linux_mmap(name, size)


def windows_mmap(name: str, size: int) -> mmap.mmap:
    """Windows mmap"""
    return mmap.mmap(-1, size, name)


def linux_mmap(name: str, size: int) -> mmap.mmap:
    """Linux mmap - read data from '/dev/shm/filename' if available"""
    file = open("/dev/shm/" + name, "a+b")
    if file.tell() == 0:
        file.write(b"\0" * size)
        file.flush()
    return mmap.mmap(file.fileno(), size)


class MMapControl:
    """Memory map control"""

    __slots__ = (
        "_buffer",
        "_is_physics_file",
        "_is_static_file",
        "_mmap_buffer",
        "_mmap_name",
        "_realtime",
        "_struct",
        "data",
        "update",
    )

    def __init__(self, mmap_name: str, data_struct: ctypes.Structure) -> None:
        """Initialize memory map setting

        Args:
            mmap_name: mmap filename.
            data_struct: ctypes data structure, ex. acc_data.SharedMemoryEvent.
        """
        self._is_physics_file = (mmap_name == ACCConstants.MM_PHYSICS_FILE_NAME)
        self._is_static_file = (mmap_name == ACCConstants.MM_STATIC_FILE_NAME)
        self._buffer = bytearray()
        self._mmap_buffer = None
        self._mmap_name = mmap_name
        self._struct = data_struct
        self._realtime = None
        self.update = None
        self.data = None

    def __del__(self):
        logger.info("sharedmemory: GC: MMap %s", self._mmap_name)

    def create(self, access_mode: int = 0) -> None:
        """Create mmap instance & initial accessible copy

        Args:
            access_mode: 0 = copy access, 1 = direct access.
        """
        self._mmap_buffer = platform_mmap(
            name=self._mmap_name,
            size=ctypes.sizeof(self._struct),
        )

        if access_mode:
            self.data = self._struct.from_buffer(self._mmap_buffer)
            self.update = self.__buffer_share
        else:
            self._buffer[:] = self._mmap_buffer
            self._realtime = self._struct.from_buffer(self._mmap_buffer)
            self.data = self._struct.from_buffer(self._buffer)
            self.update = self.__buffer_copy

        mode = "Direct" if access_mode else "Copy"
        logger.info("sharedmemory: ACTIVE: %s (%s Access)", self._mmap_name, mode)

    def close(self) -> None:
        """Close memory mapping

        Create a final accessible mmap data copy before closing mmap instance.
        """
        self.data = self._struct.from_buffer_copy(self._mmap_buffer)
        self._realtime = None
        try:
            self._mmap_buffer.close()
            logger.info("sharedmemory: CLOSED: %s", self._mmap_name)
        except BufferError:
            logger.error("sharedmemory: buffer error while closing %s", self._mmap_name)
        self.update = None  # unassign update method (for proper garbage collection)

    def __buffer_share(self) -> None:
        """Share buffer access, may result data desync"""

    def __buffer_copy(self) -> None:
        """Copy buffer access, helps avoid data desync"""
        # Game resets physics data when paused, check max RPM before update
        if self._is_physics_file and self._realtime.currentMaxRPM == 0:
            self.data.currentMaxRPM = 0
            return
        # Skip if packetId stopped updating
        if not self._is_static_file and self.data.packetId == self._realtime.packetId:
            return
        self._buffer[:] = self._mmap_buffer
