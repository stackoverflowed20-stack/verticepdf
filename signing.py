"""Assinatura digital (PAdES/CMS) com certificado .pfx/.p12 — usa pyHanko."""
from __future__ import annotations

import io
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def create_self_signed(path: str, password: str, common_name: str, email: str = "",
                       days: int = 1825) -> None:
    """Cria um certificado AUTOASSINADO (útil para testes/uso interno)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    attrs = [x509.NameAttribute(NameOID.COMMON_NAME, common_name)]
    if email:
        attrs.append(x509.NameAttribute(NameOID.EMAIL_ADDRESS, email))
    name = x509.Name(attrs)
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=days))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(
                digital_signature=True, content_commitment=True, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .sign(key, hashes.SHA256()))
    enc = (serialization.BestAvailableEncryption(password.encode()) if password
           else serialization.NoEncryption())
    data = pkcs12.serialize_key_and_certificates(common_name.encode(), key, cert, None, enc)
    Path(path).write_bytes(data)


def _signature_count(pdf_bytes: bytes) -> int:
    from pyhanko.pdf_utils.reader import PdfFileReader
    return len(PdfFileReader(io.BytesIO(pdf_bytes)).embedded_signatures)


def sign_pdf(pdf_bytes: bytes, out_path: str, pfx_path: str, pfx_password: str, *,
             reason: str = "", location: str = "", visible: bool = False,
             page_index: int = 0, box: tuple[float, float, float, float] | None = None) -> None:
    """Assina (assinatura incremental, preserva as anteriores).

    box = (x0, y0, x1, y1) em coordenadas PDF (origem no canto inferior esquerdo).
    """
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields, signers
    from pyhanko.stamp import TextStampStyle

    signer = signers.SimpleSigner.load_pkcs12(
        pfx_file=pfx_path, passphrase=pfx_password.encode() if pfx_password else None)
    if signer is None:
        raise ValueError("Não foi possível ler o certificado. Verifique o arquivo e a senha.")

    field = f"Assinatura{_signature_count(pdf_bytes) + 1}"
    writer = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes))
    if visible:
        if box is None:
            raise ValueError("Posição da assinatura visível não informada.")
        fields.append_signature_field(
            writer, fields.SigFieldSpec(sig_field_name=field, on_page=page_index, box=box))
    meta = signers.PdfSignatureMetadata(field_name=field, reason=reason or None,
                                        location=location or None, md_algorithm="sha256")
    style = TextStampStyle(
        stamp_text="Assinado digitalmente por:\n%(signer)s\n%(ts)s", border_width=1) if visible else None
    pdf_signer = signers.PdfSigner(meta, signer=signer, stamp_style=style)
    with open(out_path, "wb") as fh:
        pdf_signer.sign_pdf(writer, output=fh)


def _windows_roots() -> list:
    """Certificados raiz confiáveis do Windows (para marcar emissores conhecidos)."""
    if sys.platform != "win32":
        return []
    import ssl

    from asn1crypto import x509 as asn1_x509
    roots = []
    try:
        for der, enc, _trust in ssl.enum_certificates("ROOT"):
            if enc == "x509_asn":
                try:
                    roots.append(asn1_x509.Certificate.load(der))
                except Exception:  # noqa: BLE001
                    continue
    except Exception:  # noqa: BLE001
        pass
    return roots


def verify(pdf_bytes: bytes) -> list[dict]:
    """Valida cada assinatura. Não faz acesso à rede (sem checagem de revogação)."""
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    for name in ("pyhanko", "pyhanko_certvalidator"):  # validações "falhas" são esperadas
        logging.getLogger(name).setLevel(logging.CRITICAL)
    reader = PdfFileReader(io.BytesIO(pdf_bytes))
    roots = _windows_roots()
    out = []
    for emb in reader.embedded_signatures:
        info = {"field": emb.field_name}
        try:
            vc = ValidationContext(trust_roots=roots) if roots else None
            st = validate_pdf_signature(emb, signer_validation_context=vc)
            info.update(
                signer=st.signing_cert.subject.human_friendly,
                intact=bool(st.intact), valid=bool(st.valid), trusted=bool(st.trusted),
                whole_doc=str(st.coverage.name) == "ENTIRE_FILE",
                date=st.signer_reported_dt,
                reason=emb.sig_object.get("/Reason"),
            )
        except Exception as exc:  # noqa: BLE001
            info["error"] = str(exc)
        out.append(info)
    return out
