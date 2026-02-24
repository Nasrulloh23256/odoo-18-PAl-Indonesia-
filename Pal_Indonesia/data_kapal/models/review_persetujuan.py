# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


# Model ini menyimpan status review dan persetujuan dokumen TPTR per proyek/kapal.
class TptrReviewPersetujuan(models.Model):
    _name = "tptr.review_persetujuan"
    _description = "Menyimpan data tentang status review dan persetujuan untuk dokumen TPTR"
    _order = "id desc"

    # Relasi ke data kapal/proyek utama yang sudah ada di modul.
    tp_id = fields.Many2one(
        "pal.kapal.proyek",
        string="Data Kapal & Proyek",
        required=True,
        ondelete="cascade",
    )

    # Status review internal: Ya/Tidak.
    status_review_internal = fields.Selection(
        [
            ("ya", "Ya"),
            ("tidak", "Tidak"),
        ],
        string="Status Review Internal",
        required=True,
        default="tidak",
    )

    # Status review class/owner delegate: Ya/Tidak.
    status_review_class_owner_delegate = fields.Selection(
        [
            ("ya", "Ya"),
            ("tidak", "Tidak"),
        ],
        string="Status Review Class/Owner Delegate",
        required=True,
        default="tidak",
    )

    # Flag tanda tangan pihak terkait.
    tanda_tangan_shipyard = fields.Boolean(string="Tanda Tangan Shipyard", default=False)
    tanda_tangan_class = fields.Boolean(string="Tanda Tangan Class", default=False)
    tanda_tangan_owner_delegate = fields.Boolean(string="Tanda Tangan Owner Delegate", default=False)

    # Tanggal input otomatis saat data dibuat.
    tanggal_input = fields.Datetime(
        string="Tanggal Input",
        default=fields.Datetime.now,
        readonly=True,
        copy=False,
    )

    # Validasi eksplisit agar field status review tidak pernah kosong/invalid.
    @api.constrains("status_review_internal", "status_review_class_owner_delegate")
    def _check_review_status(self):
        allowed = {"ya", "tidak"}
        for rec in self:
            if rec.status_review_internal not in allowed:
                raise ValidationError("Status Review Internal harus diisi Ya atau Tidak.")
            if rec.status_review_class_owner_delegate not in allowed:
                raise ValidationError("Status Review Class/Owner Delegate harus diisi Ya atau Tidak.")

    # Sinkronkan attachment cover sheet parent saat status review/persetujuan berubah.
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
