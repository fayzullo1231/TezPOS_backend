"""Shtrix-kod qidiruv xatolari."""


class BarcodeLookupError(Exception):
    code = "lookup_error"
    message = "Qidiruvda xatolik yuz berdi."

    def to_dict(self) -> dict:
        return {"success": False, "error": self.code, "message": self.message}


class InvalidBarcodeError(BarcodeLookupError):
    code = "invalid_barcode"
    message = "Noto'g'ri shtrix kod. EAN/UPC/GTIN (8–14 raqam) kiriting."


class NetworkError(BarcodeLookupError):
    code = "network_error"
    message = "Internet aloqasi yo'q yoki serverga ulanib bo'lmadi."


class TimeoutError(BarcodeLookupError):
    code = "timeout"
    message = "So'rov vaqti tugadi. Qayta urinib ko'ring."


class NotFoundError(BarcodeLookupError):
    code = "not_found"
    message = "Mahsulot topilmadi"


class ServerError(BarcodeLookupError):
    code = "server_error"
    message = "Tashqi server vaqtincha ishlamayapti."


class BadResponseError(BarcodeLookupError):
    code = "bad_response"
    message = "Server noto'g'ri javob qaytardi."
