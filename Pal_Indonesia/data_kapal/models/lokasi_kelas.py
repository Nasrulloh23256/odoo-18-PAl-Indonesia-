# -*- coding: utf-8 -*-

from odoo import api, fields, models


# Model ini menyimpan detail lokasi pengujian per kapal/proyek sebagai fitur lanjutan TPTR.
class TptrLokasiKelas(models.Model):
    _name = "tptr.lokasi_kelas"
    _description = "Lokasi & Kelas Pengujian TPTR"
    _order = "id desc"

    # Nama record dibuat opsional; jika kosong akan diisi otomatis saat create.
    name = fields.Char(string="Nama")

    # Relasi ke data kapal/proyek utama agar lokasi pengujian selalu terikat ke satu proyek.
    kapal_id = fields.Many2one(
        "pal.kapal.proyek",
        string="Data Kapal & Proyek",
        required=True,
        ondelete="cascade",
    )

    # Lokasi fisik/area pengujian yang diinput user.
    lokasi_pengujian = fields.Char(string="Lokasi Pengujian", required=True)

    # Jenis tes ditarik dari data kapal supaya konsisten antar modul.
    jenis_tes = fields.Selection(
        related="kapal_id.jenis_tes",
        string="Jenis Tes",
        store=True,
        readonly=True,
    )

    # Kelas pengujian mengikuti kelas kapal dari data kapal/proyek yang dipilih.
    kelas_pengujian = fields.Char(
        related="kapal_id.kelas_kapal",
        string="Kelas Pengujian",
        store=True,
        readonly=True,
    )

    # Penanda apakah sudah ada sign class pada lokasi pengujian ini.
    sign_class = fields.Boolean(string="Sign Class", default=False)

    # Tanggal input otomatis disimpan saat record dibuat.
    tanggal_input = fields.Datetime(
        string="Tanggal Input",
        default=fields.Datetime.now,
        readonly=True,
        copy=False,
    )

    # Catatan tambahan untuk informasi lapangan.
    note = fields.Text(string="Catatan")

    # Generate nama otomatis dari lokasi + nomor proyek jika user tidak mengisi name.
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name"):
                continue
            lokasi = (vals.get("lokasi_pengujian") or "").strip()
            nomor_proyek = ""
            kapal_id = vals.get("kapal_id")
            if kapal_id:
                kapal = self.env["pal.kapal.proyek"].browse(kapal_id)
                if kapal.exists():
                    nomor_proyek = kapal.nomor_proyek or ""
            if lokasi and nomor_proyek:
                vals["name"] = "%s - %s" % (lokasi, nomor_proyek)
            elif lokasi:
                vals["name"] = lokasi
            else:
                vals["name"] = "Lokasi Pengujian"
        records = super().create(vals_list)
        records._refresh_parent_cover_sheet()
        return records

    # Update cover sheet parent agar bagian zone/designer/group mengikuti perubahan lokasi terbaru.
    def _refresh_parent_cover_sheet(self):
        parents = self.mapped("kapal_id")
        if parents:
            parents._generate_cover_sheet_attachment()

    def write(self, vals):
        result = super().write(vals)
        self._refresh_parent_cover_sheet()
        return result

    def unlink(self):
        parents = self.mapped("kapal_id")
        result = super().unlink()
        if parents:
            parents._generate_cover_sheet_attachment()
        return result
