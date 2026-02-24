# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


# Model ini menyimpan referensi dokumen pendukung yang terkait ke proyek/kapal TPTR.
class TptrDokumenPendukung(models.Model):
    _name = "tptr.dokumen_pendukung"
    _description = "Menyimpan referensi dokumen pendukung TPTR"
    _order = "id desc"

    # Relasi ke data kapal/proyek utama (model existing di modul saat ini).
    tp_id = fields.Many2one(
        "pal.kapal.proyek",
        string="Data Kapal & Proyek",
        required=True,
        ondelete="cascade",
    )

    # Nomor referensi desain yang dipakai pada proyek/kapal.
    referensi_desain = fields.Char(string="Referensi Desain", required=True)

    # Nomor dokumen maker (gambar/prosedur) yang dipakai.
    dokumen_maker = fields.Char(string="Dokumen Maker", required=True)

    # Keterangan tambahan untuk kebutuhan operasional.
    keterangan = fields.Text(string="Keterangan")

    # Tanggal input otomatis saat data dibuat.
    tanggal_input = fields.Datetime(
        string="Tanggal Input",
        default=fields.Datetime.now,
        readonly=True,
        copy=False,
    )

    # Validasi agar field wajib tidak berisi spasi kosong.
    @api.constrains("referensi_desain", "dokumen_maker")
    def _check_required_text(self):
        for rec in self:
            if not (rec.referensi_desain or "").strip():
                raise ValidationError("Referensi Desain tidak boleh kosong.")
            if not (rec.dokumen_maker or "").strip():
                raise ValidationError("Dokumen Maker tidak boleh kosong.")

    # Refresh cover sheet parent supaya PDF selalu sinkron dengan dokumen pendukung terbaru.
    def _refresh_parent_cover_sheet(self):
        parents = self.mapped("tp_id")
        if parents:
            parents._generate_cover_sheet_attachment()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._refresh_parent_cover_sheet()
        return records

    def write(self, vals):
        result = super().write(vals)
        self._refresh_parent_cover_sheet()
        return result

    def unlink(self):
        parents = self.mapped("tp_id")
        result = super().unlink()
        if parents:
            parents._generate_cover_sheet_attachment()
        return result
