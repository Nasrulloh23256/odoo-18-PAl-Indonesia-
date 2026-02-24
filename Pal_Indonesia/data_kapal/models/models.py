# -*- coding: utf-8 -*-

import base64
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from odoo import api, fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


# Master ini menyimpan daftar kelas kapal (contoh: LR, Tasneef) agar user cukup pilih dari dropdown.
class PalKapalKelas(models.Model):
    _name = "pal.kapal.kelas"
    _description = "Master Kelas Kapal"
    _rec_name = "name"
    _order = "name asc"

    # Nama kelas kapal yang nanti dipilih pada form Data Kapal dan Proyek.
    name = fields.Char(string="Nama Kelas Kapal", required=True)

    # Keterangan opsional untuk mencatat informasi tambahan tentang kelas kapal.
    keterangan = fields.Text(string="Keterangan")

    # Constraint ini mencegah duplikasi nama kelas kapal di master.
    _sql_constraints = [
        (
            "pal_kapal_kelas_name_unique",
            "unique(name)",
            "Nama kelas kapal sudah ada. Gunakan nama lain.",
        ),
    ]


# Model utama ini menyimpan data kapal & proyek yang dipakai lintas proses TPTR.
# Tujuannya agar semua dokumen mengacu ke data referensi yang sama dan konsisten.
class PalKapalProyek(models.Model):
    _name = "pal.kapal.proyek"
    _table = "TPTR_Kapal_Proyek"
    _description = "Data Kapal dan Proyek"
    _rec_name = "nama_kapal"
    _order = "id desc"

    # Nama kapal adalah identitas utama kapal yang akan muncul di dokumen TPTR.
    nama_kapal = fields.Char(string="Nama Kapal", required=True)

    # Nomor proyek dipakai sebagai identitas proyek yang terkait dengan kapal.
    nomor_proyek = fields.Char(string="Nomor Proyek", required=True, copy=False)

    # Field relasi ini dipakai di form agar user memilih kelas kapal dari master (bukan ketik manual).
    kelas_kapal_id = fields.Many2one(
        "pal.kapal.kelas",
        string="Kelas Kapal",
        required=True,
        ondelete="restrict",
    )

    # Field string ini tetap disimpan sesuai kebutuhan tabel awal, nilainya mengikuti kelas master terpilih.
    kelas_kapal = fields.Char(
        string="Kelas Kapal (Teks)",
        related="kelas_kapal_id.name",
        store=True,
        readonly=True,
    )

    # Delegasi pemilik menyimpan nama perwakilan pemilik kapal pada proyek tersebut.
    delegasi_pemilik = fields.Char(
        string="Delegasi Pemilik",
        required=True,
    )

    # QA mengunggah simbol proyek di sini agar area PROJECT SYMBOL pada cover bisa terisi otomatis.
    project_symbol = fields.Image(
        string="Project Symbol",
        max_width=512,
        max_height=512,
    )

    # Jenis tes dibatasi HAT/SAT karena dipakai sebagai parameter proses pengujian.
    jenis_tes = fields.Selection(
        [
            ("hat", "HAT"),
            ("sat", "SAT"),
        ],
        string="Jenis Tes",
        required=True,
        default="hat",
    )

    # Tanggal input otomatis diisi saat record dibuat untuk jejak waktu pencatatan data.
    tanggal_input = fields.Datetime(
        string="Tanggal Input",
        default=fields.Datetime.now,
        readonly=True,
        copy=False,
    )

    # Relasi balik ke fitur lokasi & kelas pengujian agar bisa dikelola langsung dari form kapal.
    lokasi_ids = fields.One2many(
        "tptr.lokasi_kelas",
        "kapal_id",
        string="Lokasi & Kelas Pengujian",
    )

    # Relasi dokumen pendukung untuk mengelola referensi desain & maker per proyek/kapal.
    dokumen_ids = fields.One2many(
        "tptr.dokumen_pendukung",
        "tp_id",
        string="Dokumen Pendukung",
    )

    # Relasi status review & persetujuan dokumen TPTR per proyek/kapal.
    review_ids = fields.One2many(
        "tptr.review_persetujuan",
        "tp_id",
        string="Review & Persetujuan",
    )

    # Tombol ini dipakai untuk mengunduh cover sheet PDF dari form Data Kapal & Proyek.
    def action_download_cover_sheet(self):
        self.ensure_one()
        return self.env.ref("data_kapal.action_report_tptr_cover_sheet").report_action(self)

    # Tombol ini dipakai untuk mengunduh cover sheet dari JasperReports Server (eksternal).
    def action_download_cover_sheet_jasper(self):
        self.ensure_one()
        pdf_content = self._get_jasper_cover_sheet_pdf()
        filename = "Cover Sheet Jasper - %s.pdf" % (self.nomor_proyek or self.id)
        attachment = self.env["ir.attachment"].create(
            {
                "name": filename,
                "type": "binary",
                "datas": base64.b64encode(pdf_content),
                "res_model": self._name,
                "res_id": self.id,
                "mimetype": "application/pdf",
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    # Ambil konfigurasi Jasper dari ir.config_parameter agar endpoint eksternal tidak hardcoded di kode.
    def _get_jasper_config(self):
        params = self.env["ir.config_parameter"].sudo()
        base_url = (params.get_param("data_kapal.jasper_base_url") or "").strip()
        report_unit = (params.get_param("data_kapal.jasper_report_unit") or "").strip()
        username = (params.get_param("data_kapal.jasper_username") or "").strip()
        password = params.get_param("data_kapal.jasper_password") or ""

        if not base_url or not report_unit or not username or not password:
            raise UserError(
                "Konfigurasi Jasper belum lengkap. Isi parameter: "
                "data_kapal.jasper_base_url, data_kapal.jasper_report_unit, "
                "data_kapal.jasper_username, data_kapal.jasper_password."
            )

        # Report unit harus mengarah ke path repository Jasper Server, bukan path file .jrxml lokal.
        if report_unit.lower().endswith(".jrxml") or "\\" in report_unit or ":" in report_unit:
            raise UserError(
                "Parameter data_kapal.jasper_report_unit tidak valid. "
                "Gunakan path report di repository Jasper Server (contoh: /reports/TPTR/cover_sheet_report), "
                "bukan path file lokal .jrxml."
            )

        if not report_unit.startswith("/"):
            report_unit = "/" + report_unit
        return base_url.rstrip("/"), report_unit, username, password

    # Mapping data TPTR ke parameter Jasper report supaya cover sheet bisa terisi otomatis.
    def _get_jasper_cover_sheet_params(self):
        cover = self._get_cover_sheet_data()
        first_revision = (cover.get("revision_rows") or [{}])[0]
        common_values = {
            "project_name": cover["project_name"],
            "project_no": cover["project_no"],
            "owner": cover["owner"],
            "class_name": cover["class_name"],
            "drawing_document_name": cover["drawing_document_name"],
            "drw_document_no": cover["drw_document_no"],
            "designer": cover["designer"],
            "group_name": cover["group_name"],
            "scale": cover["scale"],
            "size": cover["size"],
            "sheet_label": cover["sheet_label"],
            "year": str(cover["year"]),
            "approval_date": cover["approval_date"],
            "project_symbol_url": cover["project_symbol_url"],
            "generated_at": fields.Datetime.to_string(fields.Datetime.now()),
            "tp_id": str(self.id),
        }
        return {
            # Parameter snake_case dipakai desain report yang lama.
            **common_values,
            # Parameter PascalCase dipakai JRXML baru yang dibuat di Jaspersoft Studio.
            "ProjectName": common_values["project_name"],
            "ProjectNo": common_values["project_no"],
            "Owner": common_values["owner"],
            "Class": common_values["class_name"],
            "DrawingName": common_values["drawing_document_name"],
            "Scale": common_values["scale"],
            "Sheet": str(first_revision.get("sheet") or ""),
            "Index": str(first_revision.get("index") or ""),
            "Rev": str(first_revision.get("rev") or ""),
            "Modification": str(first_revision.get("modification") or ""),
            "Zone": str(first_revision.get("zone") or ""),
            "Date": common_values["approval_date"],
            "ProjectSymbolUrl": common_values["project_symbol_url"],
        }

    # URL publik bertoken ini dipakai Jasper Server untuk mengambil gambar simbol langsung dari Odoo.
    def _get_project_symbol_image_url(self):
        self.ensure_one()
        # Fallback ini memastikan Jasper tidak pernah menerima path gambar kosong.
        placeholder_rel = "/data_kapal/static/src/img/project_symbol_placeholder.png"

        base_url = (self.env["ir.config_parameter"].sudo().get_param("web.base.url") or "").strip().rstrip("/")
        if not base_url:
            return ""

        if not self.project_symbol:
            return "%s%s" % (base_url, placeholder_rel)

        attachment = self.env["ir.attachment"].sudo().search(
            [
                ("res_model", "=", self._name),
                ("res_id", "=", self.id),
                ("res_field", "=", "project_symbol"),
                ("type", "=", "binary"),
            ],
            order="id desc",
            limit=1,
        )
        if not attachment:
            return "%s%s" % (base_url, placeholder_rel)

        token_result = attachment.generate_access_token()
        access_token = token_result[0] if isinstance(token_result, list) and token_result else attachment.access_token
        if access_token:
            return "%s/web/image/%s?access_token=%s" % (base_url, attachment.id, access_token)
        return "%s/web/image/%s" % (base_url, attachment.id)

    # Request PDF ke JasperReports Server melalui REST API.
    def _get_jasper_cover_sheet_pdf(self):
        self.ensure_one()
        base_url, report_unit, username, password = self._get_jasper_config()
        endpoint = "%s/rest_v2/reports%s.pdf" % (base_url, report_unit)
        query = urlencode(self._get_jasper_cover_sheet_params())
        request_url = "%s?%s" % (endpoint, query)

        auth_value = base64.b64encode(("%s:%s" % (username, password)).encode("utf-8")).decode("ascii")
        req = Request(request_url)
        req.add_header("Authorization", "Basic %s" % auth_value)
        req.add_header("Accept", "application/pdf")

        try:
            with urlopen(req, timeout=90) as response:
                pdf_content = response.read()
        except HTTPError as exc:
            raise UserError("Jasper error HTTP %s: %s" % (exc.code, exc.reason))
        except URLError as exc:
            raise UserError("Gagal koneksi ke Jasper Server: %s" % exc.reason)

        if not pdf_content:
            raise UserError("Jasper tidak mengembalikan konten PDF.")
        return pdf_content

    # Kumpulan data ini dipakai template QWeb untuk mengisi cover sheet secara otomatis.
    def _get_cover_sheet_data(self):
        self.ensure_one()
        dok_model = self.env["tptr.dokumen_pendukung"]
        lokasi_model = self.env["tptr.lokasi_kelas"]
        review_model = self.env["tptr.review_persetujuan"]

        latest_dokumen = dok_model.search([("tp_id", "=", self.id)], order="tanggal_input desc, id desc", limit=1)
        latest_lokasi = lokasi_model.search([("kapal_id", "=", self.id)], order="tanggal_input desc, id desc", limit=1)
        latest_review = review_model.search([("tp_id", "=", self.id)], order="tanggal_input desc, id desc", limit=1)
        review_rows = review_model.search([("tp_id", "=", self.id)], order="tanggal_input desc, id desc", limit=8)

        def _yes_no(value):
            return "Ya" if value else "Tidak"

        table_rows = []
        for idx, row in enumerate(review_rows, start=1):
            table_rows.append(
                {
                    "sheet": idx,
                    "index": idx,
                    "rev": row.status_review_internal and row.status_review_internal.upper() or "-",
                    "modification": row.status_review_class_owner_delegate and row.status_review_class_owner_delegate.upper() or "-",
                    "zone": latest_lokasi.lokasi_pengujian if latest_lokasi else "-",
                    "date": fields.Datetime.to_string(row.tanggal_input) if row.tanggal_input else "-",
                    "drawn_by": _yes_no(row.tanda_tangan_shipyard),
                    "designed_by": _yes_no(row.tanda_tangan_class),
                    "checked_by": _yes_no(row.tanda_tangan_owner_delegate),
                    "approved_by": _yes_no(row.tanda_tangan_owner_delegate),
                }
            )

        while len(table_rows) < 8:
            table_rows.append(
                {
                    "sheet": "",
                    "index": "",
                    "rev": "",
                    "modification": "",
                    "zone": "",
                    "date": "",
                    "drawn_by": "",
                    "designed_by": "",
                    "checked_by": "",
                    "approved_by": "",
                }
            )

        now_dt = fields.Datetime.now()
        return {
            "year": now_dt.year,
            "project_name": self.nama_kapal or "-",
            "project_no": self.nomor_proyek or "-",
            "drawing_document_name": latest_dokumen.referensi_desain or "-",
            "drw_document_no": latest_dokumen.dokumen_maker or "-",
            "owner": self.delegasi_pemilik or "-",
            "class_name": self.kelas_kapal or "-",
            "designer": latest_lokasi.name if latest_lokasi else "-",
            "group_name": latest_lokasi.lokasi_pengujian if latest_lokasi else "-",
            "scale": "-",
            "size": "A4",
            "sheet_label": "1 of 1",
            "drawn_by_status": _yes_no(latest_review.tanda_tangan_shipyard) if latest_review else "Tidak",
            "designed_by_status": _yes_no(latest_review.tanda_tangan_class) if latest_review else "Tidak",
            "checked_by_status": _yes_no(latest_review.tanda_tangan_owner_delegate) if latest_review else "Tidak",
            "approved_by_status": _yes_no(latest_review.tanda_tangan_owner_delegate) if latest_review else "Tidak",
            "approval_date": fields.Datetime.to_string(latest_review.tanggal_input) if latest_review and latest_review.tanggal_input else fields.Datetime.to_string(now_dt),
            "project_symbol_url": self._get_project_symbol_image_url(),
            "revision_rows": table_rows,
        }

    # Generate attachment PDF saat data disimpan agar cover sheet selalu siap diunduh.
    def _generate_cover_sheet_attachment(self):
        if self.env.context.get("skip_cover_sheet_autogen"):
            return

        report = self.env.ref("data_kapal.action_report_tptr_cover_sheet", raise_if_not_found=False)
        if not report:
            return

        attachment_model = self.env["ir.attachment"]
        for record in self:
            filename = "Cover Sheet - %s.pdf" % (record.nomor_proyek or record.id)
            try:
                pdf_content, _content_type = report._render_qweb_pdf(report.report_name, [record.id])
            except Exception as exc:
                # Jangan blokir transaksi create/write jika engine PDF belum siap (contoh wkhtmltopdf belum terpasang).
                _logger.warning("Gagal generate cover sheet PDF untuk %s: %s", record.display_name, exc)
                continue

            vals = {
                "name": filename,
                "type": "binary",
                "datas": base64.b64encode(pdf_content),
                "res_model": record._name,
                "res_id": record.id,
                "mimetype": "application/pdf",
            }
            existing = attachment_model.search(
                [
                    ("res_model", "=", record._name),
                    ("res_id", "=", record.id),
                    ("name", "=", filename),
                ],
                limit=1,
            )
            if existing:
                existing.write(vals)
            else:
                attachment_model.create(vals)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._generate_cover_sheet_attachment()
        return records

    def write(self, vals):
        result = super().write(vals)
        self._generate_cover_sheet_attachment()
        return result
