from odoo import models, fields


# Model ini dipakai sebagai master data lokasi, supaya data lokasi tidak diketik ulang terus.
# Dengan master ini, nanti form aset cukup pilih lokasi dari dropdown (lebih rapi dan konsisten).
class PalAssetLocation(models.Model):
    _name = "pal.asset.location"
    _description = "Master Lokasi Aset"
    _order = "name"

    # Nama lokasi yang akan tampil di dropdown pilihan lokasi.
    name = fields.Char(string="Nama Lokasi", required=True)

    # Kode lokasi opsional untuk kebutuhan identifikasi internal (contoh: DCK3, WRH1).
    code = fields.Char(string="Kode Lokasi")

    # Flag aktif/nonaktif agar lokasi lama bisa disembunyikan tanpa dihapus.
    active = fields.Boolean(string="Aktif", default=True)

    # Catatan tambahan jika perlu informasi detail lokasi.
    note = fields.Text(string="Catatan")
