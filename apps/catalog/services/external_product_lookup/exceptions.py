"""Tashqi shtrix-kod API xatolari."""


class ExternalLookupError(Exception):
    """Asosiy xato turi."""

    code = "lookup_error"
    message = "Tashqi API bilan ishlashda xatolik yuz berdi."

    def to_dict(self) -> dict:
        return {
            "success": False,
            "error": self.code,
            "message": self.message,
        }


class InvalidBarcodeError(ExternalLookupError):
    code = "invalid_barcode"
    message = "Noto'g'ri shtrix kod. EAN/UPC/GTIN (8–14 raqam) kiriting."


class ProductNotFoundError(ExternalLookupError):
    code = "not_found"
    message = "Mahsulot topilmadi"


class NetworkError(ExternalLookupError):
    code = "network_error"
    message = "Internet aloqasi yo'q yoki serverga ulanib bo'lmadi."


class TimeoutError(ExternalLookupError):
    code = "timeout"
    message = "So'rov vaqti tugadi. Qayta urinib ko'ring."


class ServerError(ExternalLookupError):
    code = "server_error"
    message = "Tashqi server vaqtincha ishlamayapti. Keyinroq urinib ko'ring."


class BadResponseError(ExternalLookupError):
    code = "bad_response"
    message = "Server noto'g'ri javob qaytardi."
