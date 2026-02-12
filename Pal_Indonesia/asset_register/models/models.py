from odoo import fields, models


# Model aset utama untuk CRUD. Lokasi sekarang dihubungkan ke master lokasi agar input konsisten
# dan user cukup memilih dari daftar, bukan mengetik ulang lokasi setiap kali menambah aset.
class PalAsset(models.Model):
    _name = "pal.asset"
    _description = "Asset & Tool Register"

    # Identitas dasar aset yang wajib diisi agar data mudah dibedakan dan ditelusuri.
    name = fields.Char(string="Nama Aset", required=True)
    code = fields.Char(string="Kode Aset", required=True)

    # Relasi ke master lokasi supaya nilai lokasi terstandar dan bisa dipakai ulang antar aset.
    location_id = fields.Many2one(
        "pal.asset.location",
        string="Lokasi",
        ondelete="restrict",
    )

    # Status kondisi untuk monitoring sederhana dan filter operasional.
    condition = fields.Selection(
        [
            ("baik", "Baik"),
            ("rusak", "Rusak"),
            ("perbaikan", "Perbaikan"),
        ],
        string="Kondisi",
        default="baik",
    )
    purchase_date = fields.Date(string="Tanggal Beli")
