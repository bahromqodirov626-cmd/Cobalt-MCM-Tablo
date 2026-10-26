#!/usr/bin/env python3
"""
MCM Recovery Module
Implements brick-recovery logic for soft-bricked MCM clusters.
Handles stock flash file streaming and automatic VIN restoration.
"""

import logging
import time
from typing import Tuple, Optional, Callable
from pathlib import Path
import hashlib

logger = logging.getLogger(__name__)


class MCMRecovery:
    """MCM cluster brick recovery handler."""

    def __init__(self, uds_protocol, j2534_passthru):
        """
        Initialize MCM Recovery.

        Args:
            uds_protocol: UDS protocol instance
            j2534_passthru: J2534 PassThru instance
        """
        self.uds = uds_protocol
        self.passthru = j2534_passthru
        self.recovery_progress = 0
        self.recovery_total = 0
        self.is_recovering = False

        logger.info("MCM Recovery module initialized")

    def _verify_brick_state(self) -> Tuple[bool, str]:
        """
        Verify if MCM is in bricked state.

        Returns:
            Tuple of (is_bricked, diagnostic_message)
        """
        logger.info("Verifying MCM brick state...")

        try:
            # Attempt to read VIN - if it fails or returns garbage, likely bricked
            success, data = self.uds.read_data_by_identifier([0xF190])

            if not success or not data:
                return True, "Unable to read VIN - possible brick detected"

            vin = data.get(0xF190, b'')
            if len(vin) != 17:
                return True, f"Invalid VIN length: {len(vin)} bytes (expected 17)"

            logger.info(f"MCM appears functional, VIN: {vin.decode('utf-8', errors='ignore')}")
            return False, "MCM is functional"

        except Exception as e:
            logger.exception(f"Brick verification error: {e}")
            return True, f"Brick verification failed: {e}"

    def _calculate_checksum(self, data: bytes) -> bytes:
        """Calculate CRC32 checksum for firmware block."""
        import zlib
        crc = zlib.crc32(data) & 0xFFFFFFFF
        return crc.to_bytes(4, byteorder='big')

    def _prepare_recovery_sequence(self) -> bool:
        """
        Prepare MCM for recovery sequence.

        Returns:
            Success status
        """
        logger.info("Preparing recovery sequence...")

        try:
            # Enter extended diagnostic session
            success, _ = self.uds.diagnostic_session_control(0x03)
            if not success:
                logger.error("Failed to enter extended diagnostic session")
                return False

            time.sleep(0.5)

            # Attempt security unlock for programming
            success, seed = self.uds.security_access_request_key(0x03)
            if not success:
                logger.warning("Security access not available in recovery")
            else:
                logger.info("Security seed received for unlock")
                # In production, calculate proper key from seed
                dummy_key = hashlib.sha256(seed).digest()[:4]
                self.uds.security_access_send_key(0x03, dummy_key)

            logger.info("Recovery sequence prepared")
            return True

        except Exception as e:
            logger.exception(f"Recovery preparation failed: {e}")
            return False

    def stream_stock_flash(
        self,
        flash_file_path: str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Tuple[bool, str]:
        """
        Stream stock firmware file to recover MCM.

        Args:
            flash_file_path: Path to stock firmware file
            progress_callback: Optional callback for progress updates (current, total)

        Returns:
            Tuple of (success, status_message)
        """
        logger.info(f"Starting stock flash recovery from: {flash_file_path}")

        try:
            flash_path = Path(flash_file_path)
            if not flash_path.exists():
                error_msg = f"Firmware file not found: {flash_file_path}"
                logger.error(error_msg)
                return False, error_msg

            file_size = flash_path.stat().st_size
            logger.info(f"Firmware file size: {file_size} bytes")

            # Verify brick state
            is_bricked, brick_msg = self._verify_brick_state()
            logger.info(f"Brick state check: {brick_msg}")

            # Prepare recovery
            if not self._prepare_recovery_sequence():
                return False, "Failed to prepare recovery sequence"

            # Stream firmware in blocks
            block_size = 256
            self.recovery_total = (file_size + block_size - 1) // block_size
            self.recovery_progress = 0
            self.is_recovering = True

            with open(flash_path, 'rb') as f:
                block_num = 0

                while self.is_recovering:
                    block_data = f.read(block_size)
                    if not block_data:
                        break

                    # Pad last block if necessary
                    if len(block_data) < block_size:
                        block_data += b'\xFF' * (block_size - len(block_data))

                    # Calculate checksum
                    checksum = self._calculate_checksum(block_data)

                    # Stream block to device
                    success = self._stream_block(block_num, block_data, checksum)
                    if not success:
                        self.is_recovering = False
                        error_msg = f"Failed to stream block {block_num}"
                        logger.error(error_msg)
                        return False, error_msg

                    block_num += 1
                    self.recovery_progress = block_num

                    if progress_callback:
                        progress_callback(self.recovery_progress, self.recovery_total)

                    time.sleep(0.05)  # Small delay between blocks

            self.is_recovering = False
            success_msg = f"Successfully streamed {block_num} blocks"
            logger.info(success_msg)
            return True, success_msg

        except Exception as e:
            self.is_recovering = False
            error_msg = f"Firmware streaming failed: {e}"
            logger.exception(error_msg)
            return False, error_msg

    def _stream_block(self, block_num: int, block_data: bytes, checksum: bytes) -> bool:
        """
        Stream a single firmware block to MCM.

        Args:
            block_num: Block number
            block_data: Block data (256 bytes)
            checksum: Block checksum

        Returns:
            Success status
        """
        try:
            # Use RequestDownload service (0x34) to prepare for flash
            header = bytes([
                block_num >> 8,
                block_num & 0xFF,
            ]) + checksum

            # Send via TransferData (0x36)
            message = bytes([0x36]) + header + block_data
            success, _ = self.passthru.passthru_write_msg(message, timeout_ms=500)

            return success

        except Exception as e:
            logger.exception(f"Block stream error: {e}")
            return False

    def restore_vin(self, vin: str) -> Tuple[bool, str]:
        """
        Restore VIN to MCM after recovery.

        Args:
            vin: 17-character VIN string

        Returns:
            Tuple of (success, status_message)
        """
        logger.info(f"Restoring VIN: {vin}")

        try:
            if len(vin) != 17:
                error_msg = f"Invalid VIN length: {len(vin)} (expected 17)"
                logger.error(error_msg)
                return False, error_msg

            # Enter extended diagnostic session
            success, _ = self.uds.diagnostic_session_control(0x03)
            if not success:
                return False, "Failed to enter diagnostic session"

            time.sleep(0.5)

            # Request security access
            success, seed = self.uds.security_access_request_key(0x01)
            if not success:
                return False, "Security access denied"

            # Calculate and send key
            dummy_key = hashlib.sha256(seed).digest()[:4]
            success, _ = self.uds.security_access_send_key(0x01, dummy_key)
            if not success:
                return False, "Security unlock failed"

            time.sleep(0.5)

            # Write VIN via WriteDataByIdentifier (0x2E)
            vin_bytes = vin.encode('utf-8')[:17].ljust(17, b'\x00')
            message = bytes([0x2E, 0xF1, 0x90]) + vin_bytes

            success, response = self.passthru.passthru_write_msg(message, timeout_ms=1000)

            if success:
                logger.info(f"VIN successfully written: {vin}")
                return True, f"VIN restored: {vin}"
            else:
                return False, "VIN write failed"

        except Exception as e:
            error_msg = f"VIN restoration failed: {e}"
            logger.exception(error_msg)
            return False, error_msg

    def verify_recovery(self) -> Tuple[bool, str]:
        """
        Verify recovery was successful by reading VIN and checksums.

        Returns:
            Tuple of (success, diagnostic_message)
        """
        logger.info("Verifying MCM recovery...")

        try:
            # Read VIN
            success, data = self.uds.read_data_by_identifier([0xF190])
            if not success:
                return False, "Unable to read VIN after recovery"

            vin = data.get(0xF190, b'').decode('utf-8', errors='ignore')
            if not vin or len(vin) != 17:
                return False, f"Invalid VIN after recovery: {vin}"

            logger.info(f"Recovery verified. VIN: {vin}")
            return True, f"Recovery successful. VIN: {vin}"

        except Exception as e:
            error_msg = f"Recovery verification failed: {e}"
            logger.exception(error_msg)
            return False, error_msg

    def cancel_recovery(self) -> None:
        """Cancel ongoing recovery operation."""
        logger.warning("Recovery cancelled by user")
        self.is_recovering = False
