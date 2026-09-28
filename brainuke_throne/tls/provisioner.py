"""
brainuke_throne/tls/provisioner.py
Automated Root CA, Multi-SAN Leaf Cert, and Port 8080/8443 Provisioning.
"""

import os
import sys
import shutil
import socket
import threading
import ipaddress
import subprocess
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Tuple, List

from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa


class TLSProvisioner:
    """Manages Root CA, Leaf Certs with SAN IP binding, and Port cleanup."""

    @staticmethod
    def free_port(port: int) -> None:
        """Kills dangling background processes on Windows occupying port."""
        if sys.platform != "win32":
            return
        try:
            res = subprocess.run(f"netstat -ano | findstr :{port}", shell=True, capture_output=True, text=True)
            if res.returncode == 0 and res.stdout:
                for line in res.stdout.strip().splitlines():
                    parts = line.split()
                    if len(parts) >= 5 and "LISTENING" in parts:
                        pid = parts[-1]
                        if pid != "0" and int(pid) != os.getpid():
                            subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    @staticmethod
    def ensure_firewall_rules() -> bool:
        """Configures Windows Defender Firewall to allow inbound TCP 8080 and 8443."""
        if sys.platform != "win32":
            return True
        try:
            subprocess.run(
                'netsh advfirewall firewall add rule name="Brainuke Throne HTTPS" dir=in action=allow protocol=TCP localport=8443 profile=any',
                shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            subprocess.run(
                'netsh advfirewall firewall add rule name="Brainuke Discovery HTTP" dir=in action=allow protocol=TCP localport=8080 profile=any',
                shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return True
        except Exception:
            return False

    @staticmethod
    def ensure_adb_reverse() -> bool:
        """Configures ADB reverse port forwarding (8443, 8080, 8081) for connected Android devices."""
        def task():
            try:
                for port in (8443, 8080, 8081):
                    subprocess.run(
                        f"adb reverse tcp:{port} tcp:{port}",
                        shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=2
                    )
            except Exception:
                pass
        threading.Thread(target=task, daemon=True).start()
        return True

    @staticmethod
    def get_local_ip() -> str:
        """Gets primary outbound LAN IP."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
        finally:
            s.close()

    @classmethod
    def get_all_local_ips(cls) -> List[str]:
        """Discovers all local network adapter IPs."""
        ips = {cls.get_local_ip()}
        try:
            hostname = socket.gethostname()
            for info in socket.getaddrinfo(hostname, None):
                ip = info[4][0]
                if ip and not ip.startswith("127."):
                    ips.add(ip)
        except Exception:
            pass

        valid_ips = []
        for ip in sorted(ips):
            try:
                ipaddress.ip_address(ip)
                valid_ips.append(ip)
            except Exception:
                pass
        return valid_ips

    @classmethod
    def ensure_root_ca_and_cert(
        cls,
        ca_cert_path: str = "rootCA.pem",
        ca_key_path: str = "rootCA.key",
        cert_path: str = "cert.pem",
        key_path: str = "cert.key",
        force_regen: bool = False
    ) -> Tuple[str, str, str]:
        """Creates 3072-bit Root CA and SHA-384 Leaf Certificate with multi-SAN binding."""
        if not force_regen and os.path.exists(ca_cert_path) and os.path.exists(cert_path) and os.path.exists(key_path):
            return ca_cert_path, cert_path, key_path

        local_ip = cls.get_local_ip()

        # 1. Root CA Key & Cert
        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        ca_name = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Project Brainuke Authority"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Brainuke Throne Root CA"),
        ])
        ca_ski = x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key())
        ca_aki = x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key())
        ca_cert = (
            x509.CertificateBuilder()
            .subject_name(ca_name)
            .issuer_name(ca_name)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=True,
                crl_sign=True, encipher_only=False, decipher_only=False
            ), critical=True)
            .add_extension(ca_ski, critical=False)
            .add_extension(ca_aki, critical=False)
            .sign(ca_key, hashes.SHA384())
        )

        with open(ca_key_path, "wb") as f:
            f.write(ca_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption()
            ))
        with open(ca_cert_path, "wb") as f:
            f.write(ca_cert.public_bytes(serialization.Encoding.PEM))

        # 2. Leaf Key & Multi-SAN Cert
        leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        leaf_subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, local_ip)])

        san_entries: List[x509.GeneralName] = [
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        ]
        hostname = socket.gethostname()
        if hostname and hostname != "localhost":
            try:
                san_entries.append(x509.DNSName(hostname))
            except Exception:
                pass

        for ip_str in cls.get_all_local_ips():
            try:
                ip_entry = x509.IPAddress(ipaddress.ip_address(ip_str))
                if ip_entry not in san_entries:
                    san_entries.append(ip_entry)
            except Exception:
                pass

        leaf_ski = x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key())
        leaf_aki = x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key())

        leaf_cert = (
            x509.CertificateBuilder()
            .subject_name(leaf_subject)
            .issuer_name(ca_name)
            .public_key(leaf_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
            .add_extension(x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=True,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False
            ), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(leaf_ski, critical=False)
            .add_extension(leaf_aki, critical=False)
            .sign(ca_key, hashes.SHA384())
        )

        with open(key_path, "wb") as f:
            f.write(leaf_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption()
            ))
        with open(cert_path, "wb") as f:
            f.write(leaf_cert.public_bytes(serialization.Encoding.PEM))

        return ca_cert_path, cert_path, key_path


class CADownloaderServer:
    """HTTP server on port 8080 serving only rootCA.pem."""

    @staticmethod
    def start(ca_path: str, port: int = 8080) -> HTTPServer:
        TLSProvisioner.free_port(port)

        class CAHandler(SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path in ("/rootCA.pem", "/ca", "/", "/rootCA.crt"):
                    try:
                        with open(ca_path, "rb") as f:
                            content = f.read()
                        self.send_response(200)
                        self.send_header("Content-Type", "application/x-x509-ca-cert")
                        self.send_header("Content-Disposition", 'attachment; filename="rootCA.pem"')
                        self.send_header("Content-Length", str(len(content)))
                        self.end_headers()
                        self.wfile.write(content)
                    except Exception as e:
                        self.send_error(500, f"Error: {e}")
                else:
                    self.send_error(404, "Not Found")

            def log_message(self, format, *args):
                pass

        class ReusableHTTPServer(HTTPServer):
            allow_reuse_address = True

        httpd = ReusableHTTPServer(("0.0.0.0", port), CAHandler)
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        return httpd
