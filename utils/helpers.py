#!/usr/bin/env python3
"""
Helper Utilities
Utility functions for hex-string conversions, CRC checks, and configuration byte manipulation.
"""

import logging
from typing import List, Tuple
import struct
import zlib

logger = logging.getLogger(__name__)


# Hex-String Conversions
def hex_to_bytes(hex_string: str) -> bytes:
    """
    Convert hex string to bytes.

    Args:
        hex_string: Hex string (e.g., "3C 1A FF" or "3C1AFF")

    Returns:
        Bytes object
    """
    try:
        # Remove spaces and common separators
        clean_hex = hex_string.replace(" ", "").replace(":", "").replace("-", "")
        return bytes.fromhex(clean_hex)
    except ValueError as e:
        logger.error(f"Invalid hex string: {hex_string}: {e}")
        raise ValueError(f"Invalid hex string: {hex_string}") from e


def bytes_to_hex(data: bytes, separator: str = " ") -> str:
    """
    Convert bytes to hex string.

    Args:
        data: Bytes object
        separator: Separator between bytes (default: space)

    Returns:
        Hex string
    """
    return separator.join(f"{byte:02X}" for byte in data)


def hex_dump(data: bytes, width: int = 16) -> str:
    """
    Create a hex dump representation of data.

    Args:
        data: Bytes to dump
        width: Bytes per line

    Returns:
        Formatted hex dump string
    """
    lines = []
    for offset in range(0, len(data), width):
        chunk = data[offset:offset + width]
        hex_part = " ".join(f"{byte:02X}" for byte in chunk)
        ascii_part = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
        lines.append(f"{offset:04X}: {hex_part:<{width*3}} {ascii_part}")
    return "\n".join(lines)


# CRC Calculations
def calculate_crc32(data: bytes) -> int:
    """
    Calculate CRC32 checksum.

    Args:
        data: Data to checksum

    Returns:
        CRC32 value
    """
    return zlib.crc32(data) & 0xFFFFFFFF


def calculate_crc32_bytes(data: bytes) -> bytes:
    """
    Calculate CRC32 and return as 4 bytes (big-endian).

    Args:
        data: Data to checksum

    Returns:
        CRC32 as bytes
    """
    crc = calculate_crc32(data)
    return crc.to_bytes(4, byteorder='big')


def calculate_crc16_ccitt(data: bytes, initial: int = 0xFFFF, final_xor: int = 0x0000) -> int:
    """
    Calculate CRC16-CCITT checksum.

    Args:
        data: Data to checksum
        initial: Initial CRC value
        final_xor: Final XOR value

    Returns:
        CRC16 value
    """
    crc = initial
    poly = 0x1021

    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc <<= 1
            if crc & 0x10000:
                crc ^= poly
        crc &= 0xFFFF

    return crc ^ final_xor


def calculate_crc16_ccitt_bytes(data: bytes) -> bytes:
    """
    Calculate CRC16-CCITT and return as 2 bytes (big-endian).

    Args:
        data: Data to checksum

    Returns:
        CRC16 as bytes
    """
    crc = calculate_crc16_ccitt(data)
    return crc.to_bytes(2, byteorder='big')


def calculate_checksum_8bit(data: bytes) -> int:
    """
    Calculate simple 8-bit checksum (sum of all bytes mod 256).

    Args:
        data: Data to checksum

    Returns:
        Checksum value
    """
    return (sum(data) & 0xFF)


def calculate_xor_checksum(data: bytes) -> int:
    """
    Calculate XOR checksum (XOR of all bytes).

    Args:
        data: Data to checksum

    Returns:
        XOR checksum value
    """
    result = 0
    for byte in data:
        result ^= byte
    return result


# Configuration Byte Manipulation
class ConfigByte:
    """Helper class for configuration byte operations."""

    def __init__(self, value: int = 0):
        """
        Initialize configuration byte.

        Args:
            value: Initial byte value
        """
        self.value = value & 0xFF

    def set_bit(self, bit: int) -> 'ConfigByte':
        """Set a specific bit."""
        if 0 <= bit < 8:
            self.value |= (1 << bit)
        return self

    def clear_bit(self, bit: int) -> 'ConfigByte':
        """Clear a specific bit."""
        if 0 <= bit < 8:
            self.value &= ~(1 << bit)
        return self

    def toggle_bit(self, bit: int) -> 'ConfigByte':
        """Toggle a specific bit."""
        if 0 <= bit < 8:
            self.value ^= (1 << bit)
        return self

    def get_bit(self, bit: int) -> bool:
        """Get a specific bit value."""
        if 0 <= bit < 8:
            return bool((self.value >> bit) & 1)
        return False

    def set_bits(self, bits: List[int]) -> 'ConfigByte':
        """Set multiple bits."""
        for bit in bits:
            self.set_bit(bit)
        return self

    def clear_bits(self, bits: List[int]) -> 'ConfigByte':
        """Clear multiple bits."""
        for bit in bits:
            self.clear_bit(bit)
        return self

    def get_nibble(self, nibble: int) -> int:
        """Get upper (1) or lower (0) nibble."""
        if nibble == 0:
            return self.value & 0x0F
        elif nibble == 1:
            return (self.value >> 4) & 0x0F
        return 0

    def set_nibble(self, nibble: int, value: int) -> 'ConfigByte':
        """Set upper (1) or lower (0) nibble."""
        value &= 0x0F
        if nibble == 0:
            self.value = (self.value & 0xF0) | value
        elif nibble == 1:
            self.value = (self.value & 0x0F) | (value << 4)
        return self

    def to_bytes(self) -> bytes:
        """Get as single byte."""
        return bytes([self.value])

    def to_hex(self) -> str:
        """Get as hex string."""
        return f"0x{self.value:02X}"

    def to_binary(self) -> str:
        """Get as binary string."""
        return f"0b{self.value:08b}"


# VIN and Identification Helpers
def validate_vin(vin: str) -> Tuple[bool, str]:
    """
    Validate VIN format (17 characters, no I/O/Q).

    Args:
        vin: VIN string to validate

    Returns:
        Tuple of (is_valid, message)
    """
    if len(vin) != 17:
        return False, f"VIN must be 17 characters, got {len(vin)}"

    # Check for invalid characters (I, O, Q not allowed in VIN)
    if any(char in vin.upper() for char in ['I', 'O', 'Q']):
        return False, "VIN contains invalid characters (I, O, Q)"

    # Check for alphanumeric
    if not vin.isalnum():
        return False, "VIN must contain only alphanumeric characters"

    return True, "VIN format valid"


def parse_vin(vin: str) -> dict:
    """
    Parse VIN into components.

    Args:
        vin: 17-character VIN string

    Returns:
        Dictionary with VIN components
    """
    is_valid, msg = validate_vin(vin)
    if not is_valid:
        logger.warning(f"Invalid VIN: {msg}")
        return {}

    return {
        "wmi": vin[0:3],          # World Manufacturer Identifier
        "vds": vin[3:9],          # Vehicle Descriptor Section
        "vis": vin[9:17],         # Vehicle Identifier Section
        "year_code": vin[9],      # Model year code
        "plant_code": vin[10],    # Manufacturing plant
        "serial": vin[11:17],     # Serial number
    }


# Data Structure Helpers
def pack_uint16_be(value: int) -> bytes:
    """Pack 16-bit unsigned integer as big-endian bytes."""
    return struct.pack('>H', value & 0xFFFF)


def pack_uint32_be(value: int) -> bytes:
    """Pack 32-bit unsigned integer as big-endian bytes."""
    return struct.pack('>I', value & 0xFFFFFFFF)


def unpack_uint16_be(data: bytes) -> int:
    """Unpack 16-bit unsigned integer from big-endian bytes."""
    if len(data) < 2:
        return 0
    return struct.unpack('>H', data[:2])[0]


def unpack_uint32_be(data: bytes) -> int:
    """Unpack 32-bit unsigned integer from big-endian bytes."""
    if len(data) < 4:
        return 0
    return struct.unpack('>I', data[:4])[0]


def pad_data(data: bytes, length: int, pad_value: int = 0xFF) -> bytes:
    """
    Pad data to specified length.

    Args:
        data: Data to pad
        length: Target length
        pad_value: Padding byte value

    Returns:
        Padded data
    """
    if len(data) >= length:
        return data[:length]
    return data + bytes([pad_value] * (length - len(data)))


# Temperature and Sensor Helpers
def celsius_to_raw(celsius: float, offset: float = 40.0, scale: float = 1.0) -> int:
    """
    Convert Celsius temperature to raw sensor value.

    Common formula: raw = (celsius + offset) / scale

    Args:
        celsius: Temperature in Celsius
        offset: Sensor offset (typically 40 for MCM sensors)
        scale: Scale factor

    Returns:
        Raw sensor value
    """
    return int((celsius + offset) / scale) & 0xFF


def raw_to_celsius(raw: int, offset: float = 40.0, scale: float = 1.0) -> float:
    """
    Convert raw sensor value to Celsius temperature.

    Args:
        raw: Raw sensor value
        offset: Sensor offset
        scale: Scale factor

    Returns:
        Temperature in Celsius
    """
    return (raw * scale) - offset


def voltage_to_raw(voltage: float, ref_voltage: float = 5.0, bits: int = 8) -> int:
    """
    Convert voltage to raw ADC value.

    Args:
        voltage: Voltage value
        ref_voltage: Reference voltage (typically 5.0V)
        bits: ADC resolution bits

    Returns:
        Raw ADC value
    """
    max_value = (1 << bits) - 1
    raw = int((voltage / ref_voltage) * max_value)
    return raw & max_value


def raw_to_voltage(raw: int, ref_voltage: float = 5.0, bits: int = 8) -> float:
    """
    Convert raw ADC value to voltage.

    Args:
        raw: Raw ADC value
        ref_voltage: Reference voltage
        bits: ADC resolution bits

    Returns:
        Voltage value
    """
    max_value = (1 << bits) - 1
    return (raw / max_value) * ref_voltage


# Logging Helpers
def log_data_block(data: bytes, title: str = "Data Block") -> None:
    """Log data block with formatted hex dump."""
    logger.info(f"\n{title}:\n{hex_dump(data)}")


def log_message_exchange(direction: str, data: bytes) -> None:
    """Log sent/received message."""
    logger.debug(f"{direction}: {bytes_to_hex(data)}")
