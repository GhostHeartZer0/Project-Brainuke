"""
brainuke_core/security/key_vault.py
Hardware-Bound Entropy Key Vault via SHA3-512 & SHAKE-256 (Keccak XOF).
"""

import os
import sys
import time
import uuid
import hashlib
import subprocess
from typing import Optional, List
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class KeyVault:
    """Hardware-bound key generator and envelope encryption engine."""

    _cached_entropy: Optional[bytes] = None

    @classmethod
    def get_machine_entropy(cls) -> bytes:
        """Extracts immutable hardware identifiers and hashes with SHA3-512."""
        if cls._cached_entropy is not None:
            return cls._cached_entropy

        components: List[bytes] = [str(uuid.getnode()).encode("utf-8")]

        # 1. Windows Cryptography MachineGuid
        if sys.platform == "win32":
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
                    guid, _ = winreg.QueryValueEx(key, "MachineGuid")
                    if guid:
                        components.append(str(guid).encode("utf-8"))
            except Exception:
                pass

        # 2. Motherboard / System Hardware UUID
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            if sys.platform == "win32":
                cmd = ["wmic", "csproduct", "get", "UUID"]
            else:
                cmd = ["cat", "/sys/class/dmi/id/product_uuid"]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=2, creationflags=flags)
            if result.returncode == 0:
                lines = [line.strip() for line in result.stdout.splitlines() if line.strip() and "UUID" not in line]
                if lines:
                    components.append(lines[0].encode("utf-8"))
        except Exception:
            pass

        # 3. Fallback /proc/sys/kernel/random/boot_id or /etc/machine-id for Linux
        if sys.platform != "win32":
            for fallback_path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                if os.path.exists(fallback_path):
                    try:
                        with open(fallback_path, "rb") as f:
                            components.append(f.read().strip())
                        break
                    except Exception:
                        pass

        combined = b"|".join(components)
        cls._cached_entropy = hashlib.sha3_512(combined).digest()
        return cls._cached_entropy

    @classmethod
    def derive_symmetric_key(cls, length: int = 32) -> bytes:
        """Derives symmetric AES-256 key via SHAKE-256 XOF."""
        entropy = cls.get_machine_entropy()
        return hashlib.shake_256(entropy).digest(length)

    @classmethod
    def generate_token(cls, length_chars: int = 32) -> str:
        """Generates deterministic machine-bound auth token."""
        return cls.get_machine_entropy().hex()[:length_chars]

    @classmethod
    def generate_nonce(cls, extra: bytes = b"") -> bytes:
        """Generates 96-bit (12-byte) AES-GCM nonce using hardware entropy + timestamp."""
        entropy = cls.get_machine_entropy()
        seed = os.urandom(16) + time.monotonic_ns().to_bytes(8, "big") + entropy + extra
        return hashlib.shake_256(seed).digest(12)

    @classmethod
    def encrypt(cls, plaintext: str) -> str:
        """Envelope encrypts text to pqc_v1 payload."""
        key = cls.derive_symmetric_key(32)
        nonce = cls.generate_nonce()
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return f"pqc_v1:{(nonce + ciphertext).hex()}"

    @classmethod
    def decrypt(cls, key_blob: str) -> str:
        """Decrypts pqc_v1 payload. Enforces hardware binding."""
        if not key_blob.startswith("pqc_v1:"):
            raise ValueError("Payload missing pqc_v1: header.")

        raw_payload = bytes.fromhex(key_blob[7:])
        if len(raw_payload) < 28:  # 12-byte nonce + 16-byte GCM tag min
            raise ValueError("Corrupt key payload.")

        nonce, ciphertext = raw_payload[:12], raw_payload[12:]
        key = cls.derive_symmetric_key(32)

        try:
            return AESGCM(key).decrypt(nonce, ciphertext, None).decode("utf-8")
        except Exception:
            raise PermissionError("Hardware mismatch: cannot decrypt on this machine.")
