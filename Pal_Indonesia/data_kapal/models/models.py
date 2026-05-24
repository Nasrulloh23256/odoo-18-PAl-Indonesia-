# -*- coding: utf-8 -*-

import base64
import html
import logging
import re
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from PyPDF2 import PdfMerger, PdfReader
from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.modules.module import get_module_resource
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


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

    # Template dokumen menentukan varian dokumen TPTR yang dipakai sejak awal wizard.
    template_tptr = fields.Selection(
        [
            ("rhib", "RHIB"),
            ("davits_rhib", "DAVITS FOR RHIB"),
        ],
        string="Template TPTR",
        required=True,
        default="rhib",
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

    # Data halaman body TPTR halaman 5 disimpan langsung di proyek agar preview/download konsisten.
    body_test_related_project_no = fields.Char(string="Pengujian untuk Nomor Proyek")
    body_contract_specification = fields.Text(string="Spesifikasi Kontrak")
    body_supporting_reference = fields.Text(string="Referensi Pendukung")
    body_condition = fields.Text(string="Kondisi Pengujian")
    body_time = fields.Text(string="Waktu Pengujian")
    test_record_general_date = fields.Date(string="Tanggal Test Record")
    test_record_general_place = fields.Char(string="Tempat Test Record")
    test_record_general_team_leader = fields.Char(string="Ketua Tim PT PAL")
    test_record_general_members = fields.Text(string="Anggota Tim")
    test_record_general_delegate_name = fields.Char(string="Nama Delegate Team")
    test_record_general_class_surveyor_name = fields.Char(string="Nama Class Surveyor")

    # Fields untuk Test Record Spesifikasi Obyek & Persiapan (Halaman 8/9/11)
    # Davit Specifications
    davit_maker = fields.Char(string="Davit Maker", default="PT ATHIRA MARITIM INDONESIA")
    davit_model = fields.Char(string="Davit Model", default="ATH-RHIB-50KN")
    davit_type = fields.Char(string="Davit Type", default="RHIB50-6.1M-SL")
    davit_hoisting_speed = fields.Char(string="Davit Hoisting Speed", default="10 meter / menit")
    davit_lifting_height = fields.Char(string="Davit Lifting Height", default="15 Meter")
    davit_swl = fields.Char(string="Davit SWL", default="50 KN (5,1 TON)")
    davit_number = fields.Char(string="Davit Number", default="2 (DUA) UNIT / (units)")
    
    # Davit Preparations
    prep_davit_inspector = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="QA Inspector Reports Davits Readiness", default="ok")
    prep_davit_attendance = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Attendance of Test Team", default="ok")
    prep_davit_document = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Davit Documents Available", default="ok")
    prep_davit_equipment = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Equipment Available (Davits)", default="ok")

    # Davit Test Results & Safety Checks (Step 8)
    davit_test_load = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Davit Load Test", default="ok")
    davit_test_lifting = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Davit Lifting Test", default="ok")
    davit_test_lowering = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Davit Lowering Test", default="ok")
    davit_hoist_time_lift = fields.Char(string="Davit Hoisting Time (Lifting)", default="1.5")
    davit_hoist_press_lift = fields.Char(string="Davit Hoisting Pressure (Lifting)", default="140")
    davit_hoist_time_lower = fields.Char(string="Davit Hoisting Time (Lowering)", default="1.8")
    davit_hoist_press_lower = fields.Char(string="Davit Hoisting Pressure (Lowering)", default="150")
    davit_safe_relief_valve = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Katup Pelepas Tekanan", default="ok")
    davit_safe_locking = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Penguncian Mekanis Silinder", default="ok")
    davit_safe_holding_valve = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Katup Penahan Beban", default="ok")
    davit_safe_stop_limit = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Hook Stop Limit Teratas", default="ok")
    davit_safe_power_fail_brake = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Rem Pengaman Saat Daya Mati", default="ok")
    davit_safe_space_heater = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Pemanas Motor & Termostat", default="ok")
    davit_panel_alarm = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Alarm Suara & Visual", default="ok")
    davit_panel_integration = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Indikasi remote & Pompa", default="ok")

    # RHIB Specifications
    rhib_maker = fields.Char(string="RHIB Maker", default="TRISETIA CIPTA PERSADA")
    rhib_loa = fields.Char(string="RHIB LOA", default="8,50 Meter")
    rhib_hull_length = fields.Char(string="RHIB Hull Length", default="7,750 Meter")
    rhib_breadth = fields.Char(string="RHIB Breadth", default="3,00 Meter")
    rhib_hull_height = fields.Char(string="RHIB Hull Height", default="1,35 Meter")
    rhib_draft = fields.Char(string="RHIB Draft", default="0.50 Meter")
    rhib_engine = fields.Char(string="RHIB Engine", default="YAMAHA F2000BETX/FL200BETX")
    rhib_number = fields.Char(string="RHIB Number", default="2 (DUA) UNIT / 2(TWO) units")
    rhib_max_speed = fields.Char(string="RHIB Max Speed", default="35,00 knots")
    rhib_cruising_speed = fields.Char(string="RHIB Cruising Speed", default="18.00 knots")
    rhib_capacity = fields.Char(string="RHIB Capacity", default="12 persons")
    rhib_boat_weight = fields.Char(string="RHIB Boat Weight", default="2260 kg")
    rhib_total_weight = fields.Char(string="RHIB Total Weight", default="3960 kg")
    rhib_assumed_weight = fields.Char(string="RHIB Assumed Weight", default="3960 kg")
    rhib_unit_count = fields.Char(string="RHIB Unit Count", default="2 (DUA) UNIT / (units)")

    # RHIB Checklist Halaman 10-12
    prep_rhib_item1 = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="QA Inspector Reports RHIB & Davits Readiness", default="ok")
    prep_rhib_item2 = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Attendance of Test Team (RHIB)", default="ok")
    prep_rhib_item3 = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Test Procedure Documents Available", default="ok")
    prep_rhib_item4 = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Test Record Equipment Available", default="ok")
    prep_rhib_item5 = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Testing Results Document (HPP) Available", default="ok")
    prep_rhib_item6 = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Check Rescue RHIB & Navigation Equipment", default="ok")
    prep_rhib_item7 = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Check Outboard Main Engine Fuel Fully Charged", default="ok")
    prep_rhib_item8 = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Check Hydraulic Steering Oil Fully Charged", default="ok")
    prep_rhib_item9 = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Weigh Rescue RHIB Before Sea Trial", default="ok")
    prep_rhib_item10 = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Safety Equipment Available", default="ok")
    prep_rhib_item11 = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Life Jacket Available", default="ok")
    prep_rhib_item12 = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Portable Ladder Available", default="ok")
    prep_rhib_item13 = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Mooring Rope Available", default="ok")
    prep_rhib_item14 = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Fender Available", default="ok")
    prep_rhib_item15 = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Paddle Available", default="ok")
    prep_rhib_item16 = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Portable Fire Extinguisher Available", default="ok")
    prep_rhib_item17 = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Safety Procedure Check", default="ok")
    prep_rhib_item18 = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Inspect Electronic Cable Installation Sequence", default="ok")
    prep_rhib_item19 = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Use Mooring Equipment When Docked", default="ok")
    prep_rhib_item20 = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Use Portable Ladder to Get On/Off Ship", default="ok")
    prep_rhib_item21 = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Fire Emergency Safety Actions", default="ok")
    prep_rhib_item22 = fields.Selection([('ok', 'OK'), ('not_ok', 'NOT OK')], string="Engine Failure Safety Actions", default="ok")

    peralatan_ids = fields.One2many("tptr.peralatan", "kapal_id", string="Peralatan Yang Digunakan")
    catatan_ids = fields.One2many("tptr.catatan", "kapal_id", string="Catatan/Remarks")

    def _get_peralatan_list(self):
        self.ensure_one()
        if not self.peralatan_ids:
            # Create on the fly to persist defaults
            self.env['tptr.peralatan'].create([
                {'kapal_id': self.id, 'name_id': 'PERALATAN KOMUNIKASI.', 'name_en': '(Communication Device (Handy Talky).)', 'sequence': 10},
                {'kapal_id': self.id, 'name_id': 'PENGUKUR WAKTU.', 'name_en': '(Stopwatch.)', 'sequence': 20},
                {'kapal_id': self.id, 'name_id': 'ALAT KESELAMATAN.', 'name_en': '(Safety Utility.)', 'sequence': 30},
            ])
        return self.peralatan_ids

    def _get_catatan_list(self):
        self.ensure_one()
        if not self.catatan_ids:
            # Create on the fly to persist defaults
            self.env['tptr.catatan'].create([
                {'kapal_id': self.id, 'remark': '', 'action': '', 'sequence': 10},
            ])
        return self.catatan_ids


    body_delegate_signature = fields.Image(
        string="Tanda Tangan Delegate Team",
        max_width=1024,
        max_height=512,
    )
    body_delegate_name = fields.Char(string="Nama Delegate Team")
    body_delegate_signature_filename = fields.Char(string="Nama File TTD Delegate Team")
    body_delegate_signature_date = fields.Date(string="Tanggal TTD Delegate Team")
    body_pt_pal_signature = fields.Image(
        string="Tanda Tangan PT PAL Indonesia",
        max_width=1024,
        max_height=512,
    )
    body_pt_pal_name = fields.Char(string="Nama PT PAL Indonesia")
    body_pt_pal_signature_filename = fields.Char(string="Nama File TTD PT PAL Indonesia")
    body_pt_pal_signature_date = fields.Date(string="Tanggal TTD PT PAL Indonesia")

    # Ringkasan ini dipakai untuk tampilan utama TPTR agar user cepat melihat status dokumen.
    nomor_dokumen_utama = fields.Char(
        string="Nomor Document",
        compute="_compute_tptr_ringkasan",
        store=True,
        readonly=True,
    )
    nama_dokumen_utama = fields.Char(
        string="Nama Document",
        compute="_compute_tptr_ringkasan",
        store=True,
        readonly=True,
    )
    tanggal_dibuat_document = fields.Datetime(
        string="Tanggal Dibuat Document",
        compute="_compute_tptr_ringkasan",
        store=True,
        readonly=True,
    )
    terakhir_diedit_document = fields.Datetime(
        string="Terakhir Diedit",
        compute="_compute_tptr_ringkasan",
        store=True,
        readonly=True,
    )
    status_tptr = fields.Char(
        string="Status",
        compute="_compute_tptr_ringkasan",
        store=True,
        readonly=True,
    )

    @api.depends(
        "template_tptr",
        "body_test_related_project_no",
        "body_contract_specification",
        "body_supporting_reference",
        "body_condition",
        "body_time",
        "test_record_general_date",
        "test_record_general_place",
        "test_record_general_team_leader",
        "test_record_general_members",
        "test_record_general_delegate_name",
        "test_record_general_class_surveyor_name",
        "dokumen_ids.dokumen_maker",
        "dokumen_ids.referensi_desain",
        "dokumen_ids.tanggal_input",
        "dokumen_ids.create_date",
        "dokumen_ids.write_date",
        "review_ids.status_review_internal",
        "review_ids.status_review_class_owner_delegate",
        "review_ids.tanda_tangan_shipyard",
        "review_ids.tanda_tangan_class",
        "review_ids.tanda_tangan_owner_delegate",
        "review_ids.tanggal_input",
    )
    def _compute_tptr_ringkasan(self):
        # Ambil data terbaru per proyek/kapal agar list utama TPTR selalu menampilkan kondisi terakhir.
        dokumen_map = {}
        review_map = {}

        if self.ids:
            dokumen_records = self.env["tptr.dokumen_pendukung"].search(
                [("tp_id", "in", self.ids)],
                order="tp_id, tanggal_input desc, id desc",
            )
            for row in dokumen_records:
                tp_id = row.tp_id.id
                if tp_id not in dokumen_map:
                    dokumen_map[tp_id] = row

            review_records = self.env["tptr.review_persetujuan"].search(
                [("tp_id", "in", self.ids)],
                order="tp_id, tanggal_input desc, id desc",
            )
            for row in review_records:
                tp_id = row.tp_id.id
                if tp_id not in review_map:
                    review_map[tp_id] = row

        for rec in self:
            latest_dokumen = dokumen_map.get(rec.id)
            latest_review = review_map.get(rec.id)
            template_profile = rec._get_tptr_template_profile(rec.template_tptr)

            rec.nomor_dokumen_utama = latest_dokumen.dokumen_maker if latest_dokumen else template_profile["document_no"]
            rec.nama_dokumen_utama = (
                latest_dokumen.referensi_desain
                if latest_dokumen
                else template_profile["drawing_document_name"]
            )
            rec.tanggal_dibuat_document = latest_dokumen.create_date if latest_dokumen else False
            rec.terakhir_diedit_document = latest_dokumen.write_date if latest_dokumen else False

            if not latest_dokumen:
                rec.status_tptr = "Menunggu Dokumen"
                continue
            if not (rec.body_test_related_project_no or "").strip() or not (rec.body_contract_specification or "").strip():
                rec.status_tptr = "Butuh Data Body: Halaman 5"
                continue
            if not (rec.body_supporting_reference or "").strip() or not (rec.body_condition or "").strip() or not (rec.body_time or "").strip():
                rec.status_tptr = "Butuh Data Body: Halaman 6"
                continue
            if not rec._is_test_record_general_completed():
                rec.status_tptr = "Butuh Data Test Record: Halaman 8"
                continue
            if not latest_review:
                rec.status_tptr = "Butuh Persetujuan"
                continue

            pending_items = []
            if latest_review.status_review_internal != "ya":
                pending_items.append("Review Internal")
            if latest_review.status_review_class_owner_delegate != "ya":
                pending_items.append("Review Class/Owner")
            if not latest_review.tanda_tangan_shipyard:
                pending_items.append("TTD Shipyard")
            if not latest_review.tanda_tangan_class:
                pending_items.append("TTD Class")
            if not latest_review.tanda_tangan_owner_delegate:
                pending_items.append("TTD Owner Delegate")

            rec.status_tptr = (
                "Disetujui"
                if not pending_items
                else "Butuh Persetujuan: %s" % ", ".join(pending_items)
            )

    @api.model
    def _get_tptr_template_profiles(self):
        return {
            "rhib": {
                "label": "RHIB",
                "drawing_document_name": "RIGID HULL INFLATABLE BOAT (RHIB)",
                "document_no": "Q5833.00",
                "footer_label": "Q5833.00- RIGID HULL INFLATABLE BOAT (RHIB)",
            },
            "davits_rhib": {
                "label": "DAVITS FOR RHIB",
                "drawing_document_name": "DAVITS FOR RHIB",
                "document_no": "Q5833.01",
                "footer_label": "Q5833.01- DAVITS FOR RHIB",
            },
        }

    @api.model
    def _get_tptr_template_profile(self, template_key=None):
        profiles = self._get_tptr_template_profiles()
        return dict(profiles.get(template_key or "rhib", profiles["rhib"]))

    def _is_test_record_general_completed(self):
        self.ensure_one()
        if not self.test_record_general_date:
            return False
        if not (self.test_record_general_place or "").strip():
            return False
        if not (self.test_record_general_team_leader or "").strip():
            return False
        if not (self.test_record_general_members or "").strip():
            return False
        if not (self.test_record_general_delegate_name or "").strip():
            return False
        if self.template_tptr == "davits_rhib" and not (self.test_record_general_class_surveyor_name or "").strip():
            return False
        return True

    def _is_test_record_spec_completed(self):
        self.ensure_one()
        equip_ok = all(
            (e.name_id or "").strip() and (e.name_en or "").strip()
            for e in self._get_peralatan_list()
        )
        if not equip_ok:
            return False

        if self.template_tptr == "davits_rhib":
            return bool(
                (self.davit_maker or "").strip()
                and (self.davit_model or "").strip()
                and (self.davit_type or "").strip()
                and (self.davit_hoisting_speed or "").strip()
                and (self.davit_lifting_height or "").strip()
                and (self.davit_swl or "").strip()
                and (self.davit_number or "").strip()
            )
        else:
            return bool(
                (self.rhib_maker or "").strip()
                and (self.rhib_loa or "").strip()
                and (self.rhib_hull_length or "").strip()
                and (self.rhib_breadth or "").strip()
                and (self.rhib_hull_height or "").strip()
                and (self.rhib_draft or "").strip()
                and (self.rhib_engine or "").strip()
                and (self.rhib_number or "").strip()
                and (self.rhib_max_speed or "").strip()
                and (self.rhib_cruising_speed or "").strip()
                and (self.rhib_capacity or "").strip()
                and (self.rhib_boat_weight or "").strip()
                and (self.rhib_total_weight or "").strip()
                and (self.rhib_assumed_weight or "").strip()
                and (self.rhib_unit_count or "").strip()
            )

    def _is_test_procedure_checklist_completed(self):
        self.ensure_one()
        if self.template_tptr == "davits_rhib":
            return bool(
                self.prep_davit_inspector
                and self.prep_davit_attendance
                and self.prep_davit_document
                and self.prep_davit_equipment
                and self.davit_test_load
                and self.davit_test_lifting
                and self.davit_test_lowering
                and (self.davit_hoist_time_lift or "").strip()
                and (self.davit_hoist_press_lift or "").strip()
                and (self.davit_hoist_time_lower or "").strip()
                and (self.davit_hoist_press_lower or "").strip()
                and self.davit_safe_relief_valve
                and self.davit_safe_locking
                and self.davit_safe_holding_valve
                and self.davit_safe_stop_limit
                and self.davit_safe_power_fail_brake
                and self.davit_safe_space_heater
                and self.davit_panel_alarm
                and self.davit_panel_integration
            )
        return bool(
            self.prep_rhib_item1
            and self.prep_rhib_item2
            and self.prep_rhib_item3
            and self.prep_rhib_item4
            and self.prep_rhib_item5
            and self.prep_rhib_item6
            and self.prep_rhib_item7
            and self.prep_rhib_item8
            and self.prep_rhib_item9
            and self.prep_rhib_item10
            and self.prep_rhib_item11
            and self.prep_rhib_item12
            and self.prep_rhib_item13
            and self.prep_rhib_item14
            and self.prep_rhib_item15
            and self.prep_rhib_item16
            and self.prep_rhib_item17
            and self.prep_rhib_item18
            and self.prep_rhib_item19
            and self.prep_rhib_item20
            and self.prep_rhib_item21
            and self.prep_rhib_item22
        )

    # Tombol ini dipakai untuk mengunduh cover sheet PDF dari form Data Kapal & Proyek.
    def action_download_cover_sheet(self):
        self.ensure_one()
        return self.env.ref("data_kapal.action_report_tptr_cover_sheet").report_action(self)

    # Tombol ini dipakai untuk mengunduh cover sheet dari JasperReports Server (eksternal).
    def action_download_cover_sheet_jasper(self):
        self.ensure_one()
        pdf_content = self._get_jasper_combined_pdf()
        filename = "TPTR Document Jasper - %s.pdf" % (self.nomor_proyek or self.id)
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

    # Ambil kredensial utama Jasper dari ir.config_parameter agar endpoint eksternal tidak hardcoded di kode.
    def _get_jasper_connection_config(self):
        params = self.env["ir.config_parameter"].sudo()
        base_url = (params.get_param("data_kapal.jasper_base_url") or "").strip()
        username = (params.get_param("data_kapal.jasper_username") or "").strip()
        password = params.get_param("data_kapal.jasper_password") or ""

        if not base_url or not username or not password:
            raise UserError(
                "Konfigurasi Jasper belum lengkap. Isi parameter: "
                "data_kapal.jasper_base_url, data_kapal.jasper_report_unit, "
                "data_kapal.jasper_username, data_kapal.jasper_password."
            )
        return base_url.rstrip("/"), username, password

    def _normalize_jasper_report_unit(self, report_unit, param_name):
        report_unit = (report_unit or "").strip()
        if not report_unit:
            raise UserError("Parameter %s belum diisi." % param_name)

        # Report unit harus mengarah ke path repository Jasper Server, bukan path file .jrxml lokal.
        if report_unit.lower().endswith(".jrxml") or "\\" in report_unit or ":" in report_unit:
            raise UserError(
                ("Parameter %s tidak valid. " % param_name)
                + "Gunakan path report di repository Jasper Server (contoh: /reports/TPTR/cover_sheet_report), "
                + "bukan path file lokal .jrxml."
            )

        if not report_unit.startswith("/"):
            report_unit = "/" + report_unit
        return report_unit

    # Ambil konfigurasi report Jasper cover sheet.
    def _get_jasper_config(self):
        params = self.env["ir.config_parameter"].sudo()
        base_url, username, password = self._get_jasper_connection_config()
        report_unit = self._normalize_jasper_report_unit(
            params.get_param("data_kapal.jasper_report_unit"),
            "data_kapal.jasper_report_unit",
        )
        return base_url, report_unit, username, password

    # Report body TPTR dipisah ke JRXML lain agar cover tetap stabil 2 halaman.
    def _get_jasper_body_config(self):
        params = self.env["ir.config_parameter"].sudo()
        base_url, username, password = self._get_jasper_connection_config()
        report_unit = (params.get_param("data_kapal.jasper_body_report_unit") or "").strip()
        if not report_unit:
            return base_url, False, username, password
        report_unit = self._normalize_jasper_report_unit(
            report_unit,
            "data_kapal.jasper_body_report_unit",
        )
        return base_url, report_unit, username, password

    def _get_jasper_test_record_config(self):
        params = self.env["ir.config_parameter"].sudo()
        base_url, username, password = self._get_jasper_connection_config()
        report_unit = (params.get_param("data_kapal.jasper_test_record_report_unit") or "").strip()
        if not report_unit:
            return base_url, False, username, password
        report_unit = self._normalize_jasper_report_unit(
            report_unit,
            "data_kapal.jasper_test_record_report_unit",
        )
        return base_url, report_unit, username, password

    # Mapping data TPTR ke parameter Jasper report supaya cover sheet bisa terisi otomatis.
    def _get_jasper_cover_sheet_params(self):
        cover = self._get_cover_sheet_data()
        body = self._get_body_sheet_data()
        first_revision = (cover.get("revision_rows") or [{}])[0]
        intro_acceptance_rows = body.get("intro_acceptance_rows") or [{}, {}]
        delegate_row = intro_acceptance_rows[0] if intro_acceptance_rows else {}
        pt_pal_row = intro_acceptance_rows[1] if len(intro_acceptance_rows) > 1 else {}
        test_record_intro = self._get_test_record_intro_data()
        test_record_general = self._get_test_record_general_data()
        common_values = {
            "project_name": cover["project_name"],
            "project_no": cover["project_no"],
            "owner": cover["owner"],
            "class_name": cover["class_name"],
            "drawing_document_name": cover["drawing_document_name"],
            "summary_document_name": cover["summary_document_name"],
            "drw_document_no": cover["drw_document_no"],
            "designer": cover["designer"],
            "group_name": cover["group_name"],
            "scale": cover["scale"],
            "size": cover["size"],
            "sheet_label": cover["sheet_label"],
            "year": str(cover["year"]),
            "approval_date": cover["approval_date"],
            "project_symbol_url": cover["project_symbol_url"],
            "test_type_label": cover["test_type_label"],
            "project_full_label": cover["project_full_label"],
            "document_footer_label": cover["document_footer_label"],
            "summary_footer_label": cover["summary_footer_label"],
            "summary_page_number_label": cover["summary_page_number_label"],
            "body_page_number_label": cover["body_page_number_label"],
            "toc_page_number_label": cover["toc_page_number_label"],
            "intro_page_number_label": body["intro_page_number_label"],
            "procedure_page_number_label": body["procedure_page_number_label"],
            "approval_class_label": cover["approval_class_label"],
            "approval_owner_label": cover["approval_owner_label"],
            "drawn_by_date": cover["drawn_by_date"],
            "designed_by_date": cover["designed_by_date"],
            "checked_by_date": cover["checked_by_date"],
            "approved_by_date": cover["approved_by_date"],
            "intro_heading_main": body["intro_heading_main"],
            "intro_heading_sub": body["intro_heading_sub"],
            "intro_test_type_label": body["intro_test_type_label"],
            "intro_test_object_label": body["intro_test_object_label"],
            "intro_project_number_label": body["intro_project_number_label"],
            "intro_test_related_project_no": body["intro_test_related_project_no"],
            "intro_document_number": body["intro_document_number"],
            "intro_contract_specification": body["intro_contract_specification"],
            "procedure_document_markup": body["procedure_document_markup"],
            "procedure_supporting_reference_markup": body["procedure_supporting_reference_markup"],
            "procedure_condition_markup": body["procedure_condition_markup"],
            "procedure_time_markup": body["procedure_time_markup"],
            "procedure_definition_markup": body["procedure_definition_markup"],
            "test_record_intro_title": test_record_intro["title"],
            "test_record_intro_object_label": test_record_intro["object_label"],
            "test_record_project_number_label": test_record_intro["project_number_label"],
            "test_record_document_number": test_record_intro["document_number"],
            "test_record_page_number_label": test_record_intro["page_number_label"],
            "test_record_general_date": test_record_general["date"],
            "test_record_general_place": test_record_general["place"],
            "test_record_general_team_leader": test_record_general["team_leader"],
            "test_record_general_member_1": test_record_general["member_1"],
            "test_record_general_member_2": test_record_general["member_2"],
            "test_record_general_member_3": test_record_general["member_3"],
            "test_record_general_member_4": test_record_general["member_4"],
            "test_record_general_delegate_name": test_record_general["delegate_name"],
            "test_record_general_class_surveyor_name": test_record_general["class_surveyor_name"],
            "test_record_general_page_number_label": test_record_general["page_number_label"],
            "delegate_acceptance_label": delegate_row.get("acceptance") or "Delegate Team",
            "delegate_name": delegate_row.get("name") or "",
            "delegate_signature_date": delegate_row.get("date") or "",
            "delegate_signature_url": self._get_binary_field_image_url("body_delegate_signature"),
            "pt_pal_acceptance_label": pt_pal_row.get("acceptance") or "PT PAL Indonesia",
            "pt_pal_name": pt_pal_row.get("name") or "",
            "pt_pal_signature_date": pt_pal_row.get("date") or "",
            "pt_pal_signature_url": self._get_binary_field_image_url("body_pt_pal_signature"),
            # URL logo PAL dikirim sebagai parameter agar JRXML tidak memakai path lokal komputer.
            "logo_path": self._get_pal_logo_url(),
            # Fallback path lokal Jasper Server (file URI) untuk kasus HTTP image diblokir.
            "logo_local_path": self._get_pal_logo_file_uri(),
            "generated_at": fields.Datetime.to_string(fields.Datetime.now()),
            "tp_id": str(self.id),
        }
        return {
            # Parameter snake_case dipakai desain report yang lama.
            **common_values,
            # Parameter PascalCase dipakai JRXML baru yang dibuat di Jaspersoft Studio.
            "ProjectName": common_values["project_name"],
            "ProjectNo": common_values["project_no"],
            # Alias tambahan untuk kompatibilitas template Jasper dengan style naming berbeda.
            "PROJECT_NAME": common_values["project_name"],
            "PROJECT_NO": common_values["project_no"],
            "projectName": common_values["project_name"],
            "projectNo": common_values["project_no"],
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

    def _get_binary_field_image_url(self, field_name):
        self.ensure_one()
        base_url = (self.env["ir.config_parameter"].sudo().get_param("web.base.url") or "").strip().rstrip("/")
        if not base_url or not field_name or not getattr(self, field_name, False):
            return ""

        attachment = self.env["ir.attachment"].sudo().search(
            [
                ("res_model", "=", self._name),
                ("res_id", "=", self.id),
                ("res_field", "=", field_name),
                ("type", "=", "binary"),
            ],
            order="id desc",
            limit=1,
        )
        if not attachment:
            return ""

        token_result = attachment.generate_access_token()
        access_token = token_result[0] if isinstance(token_result, list) and token_result else attachment.access_token
        if access_token:
            return "%s/web/image/%s?access_token=%s" % (base_url, attachment.id, access_token)
        return "%s/web/image/%s" % (base_url, attachment.id)

    # URL absolut logo PAL untuk dipakai elemen image di JRXML melalui parameter logo_path.
    def _get_pal_logo_url(self):
        self.ensure_one()
        base_url = (self.env["ir.config_parameter"].sudo().get_param("web.base.url") or "").strip().rstrip("/")
        if not base_url:
            return ""
        return "%s/data_kapal/static/src/img/pal_logo.png" % base_url

    # Fallback file URI lokal untuk Jasper saat resource URL HTTP tidak bisa diambil.
    def _get_pal_logo_file_uri(self):
        self.ensure_one()
        logo_file = (
            get_module_resource("data_kapal", "static", "src", "img", "pal_logo.png")
            or get_module_resource("data_kapal", "assets", "img", "pal_logo.png")
        )
        if not logo_file:
            return ""
        return Path(logo_file).resolve().as_uri()

    # Request PDF ke JasperReports Server melalui REST API.
    def _request_jasper_pdf(self, report_unit, params, base_url, username, password):
        endpoint = "%s/rest_v2/reports%s.pdf" % (base_url, report_unit)
        query = urlencode(params)
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

    def _get_jasper_cover_sheet_pdf(self):
        self.ensure_one()
        base_url, report_unit, username, password = self._get_jasper_config()
        return self._request_jasper_pdf(
            report_unit,
            self._get_jasper_cover_sheet_params(),
            base_url,
            username,
            password,
        )

    def _get_jasper_body_pdf(self):
        self.ensure_one()
        base_url, report_unit, username, password = self._get_jasper_body_config()
        if not report_unit:
            raise UserError("Report body Jasper belum dikonfigurasi.")
        return self._request_jasper_pdf(
            report_unit,
            self._get_jasper_cover_sheet_params(),
            base_url,
            username,
            password,
        )

    def _get_jasper_test_record_pdf(self):
        self.ensure_one()
        base_url, report_unit, username, password = self._get_jasper_test_record_config()
        if not report_unit:
            raise UserError("Report test record Jasper belum dikonfigurasi.")
        return self._request_jasper_pdf(
            report_unit,
            self._get_jasper_cover_sheet_params(),
            base_url,
            username,
            password,
        )

    def _get_local_tptr_body_pdf(self):
        self.ensure_one()
        try:
            return self._build_local_tptr_body_pdf()
        except Exception as exc:
            _logger.warning(
                "Body TPTR lokal via ReportLab gagal untuk %s, fallback ke QWeb: %s",
                self.display_name,
                exc,
            )

        report = self.env.ref("data_kapal.action_report_tptr_body_sheet", raise_if_not_found=False)
        if not report:
            raise UserError("Template PDF body TPTR lokal tidak ditemukan.")

        try:
            pdf_content, _content_type = report._render_qweb_pdf(report.report_name, [self.id])
        except Exception as exc:
            raise UserError("Gagal membuat body TPTR lokal: %s" % exc)

        if not pdf_content:
            raise UserError("Template PDF body TPTR lokal tidak menghasilkan konten.")
        return pdf_content

    def _get_reportlab_font_names(self):
        self.ensure_one()
        fonts = {
            "regular": "Helvetica",
            "bold": "Helvetica-Bold",
            "italic": "Helvetica-Oblique",
        }
        font_map = {
            "regular": ("ArialMT-Regular", Path(r"C:\Windows\Fonts\arial.ttf")),
            "bold": ("ArialMT-Bold", Path(r"C:\Windows\Fonts\arialbd.ttf")),
            "italic": ("ArialMT-Italic", Path(r"C:\Windows\Fonts\ariali.ttf")),
        }
        registered = set(pdfmetrics.getRegisteredFontNames())
        for key, (font_name, font_path) in font_map.items():
            if font_name in registered:
                fonts[key] = font_name
                continue
            if not font_path.exists():
                continue
            try:
                pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
                fonts[key] = font_name
            except Exception:
                continue
        return fonts

    def _get_test_record_intro_data(self):
        self.ensure_one()
        template_profile = self._get_tptr_template_profile(self.template_tptr)
        current_document_no = self.nomor_dokumen_utama or template_profile["document_no"]
        project_number_display = self._get_body_project_number_display()
        project_full_display = "%s / %s" % (
            self.nama_kapal or "-",
            project_number_display or "-",
        )
        if self.template_tptr == "davits_rhib":
            return {
                "title": "Sea Acceptance Test",
                "object_label": "DAVITS FOR RIGID HULL INFLATABLE BOAT (RHIB)",
                "project_number_label": project_full_display,
                "document_number": current_document_no,
                "page_number_label": "7 / 12",
            }
        return {
            "title": "Harbor Acceptance Test",
            "object_label": "RIGID HULL INFLATABLE BOAT (RHIB)",
            "project_number_label": project_full_display,
            "document_number": current_document_no,
            "page_number_label": "9 / 16",
        }

    def _get_test_record_general_data(self):
        self.ensure_one()
        member_lines = [line.strip() for line in (self.test_record_general_members or "").replace("\r", "").split("\n") if line.strip()]
        while len(member_lines) < 4:
            member_lines.append("")
        page_num = "8 / 12" if self.template_tptr == "davits_rhib" else "10 / 16"
        return {
            "date": self.test_record_general_date.strftime("%d/%m/%Y") if self.test_record_general_date else "",
            "place": self.test_record_general_place or "",
            "team_leader": self.test_record_general_team_leader or "",
            "member_1": member_lines[0] if len(member_lines) > 0 else "",
            "member_2": member_lines[1] if len(member_lines) > 1 else "",
            "member_3": member_lines[2] if len(member_lines) > 2 else "",
            "member_4": member_lines[3] if len(member_lines) > 3 else "",
            "delegate_name": self.test_record_general_delegate_name or "",
            "class_surveyor_name": self.test_record_general_class_surveyor_name or "",
            "page_number_label": page_num,
        }

    def _build_local_tptr_test_record_intro_pdf(self):
        self.ensure_one()
        cover = self._get_cover_sheet_data()
        page7 = self._get_test_record_intro_data()
        page8 = self._get_test_record_general_data()
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        page_width, page_height = A4
        left = 42
        right = page_width - 42
        fonts = self._get_reportlab_font_names()

        def draw_wrapped_center(text, y, width, font_name, font_size, leading):
            lines = simpleSplit(text or "-", font_name, font_size, width)
            total_height = len(lines) * leading
            text_obj = pdf.beginText((page_width - width) / 2, y)
            text_obj.setFont(font_name, font_size)
            text_obj.setLeading(leading)
            for line in lines:
                line_width = pdfmetrics.stringWidth(line, font_name, font_size)
                text_obj.setXPos((width - line_width) / 2)
                text_obj.textLine(line)
            pdf.drawText(text_obj)
            return y - total_height

        def draw_header():
            pdf.setStrokeColor(colors.HexColor("#666666"))
            pdf.setFillColor(colors.HexColor("#666666"))
            pdf.setLineWidth(0.8)
            header_y = page_height - 72
            pdf.line(left, header_y, right, header_y)
            pdf.setFont(fonts["bold"], 9)
            pdf.drawString(left, header_y + 10, "DIVISION OF QA")
            pdf.drawString(left, header_y, "TEST RECORD")
            pdf.setFont(fonts["regular"], 9)
            pdf.drawRightString(right, header_y + 3, cover["project_name"])
            return header_y

        def draw_footer(page_label):
            footer_y = 52
            pdf.setStrokeColor(colors.HexColor("#666666"))
            pdf.line(left, footer_y + 10, right, footer_y + 10)
            pdf.setFillColor(colors.HexColor("#666666"))
            pdf.setFont(fonts["regular"], 7)
            pdf.drawString(left, footer_y, cover["summary_footer_label"])
            pdf.drawRightString(right, footer_y, page_label)

        def draw_checkmark(cx, cy):
            pdf.setStrokeColor(colors.black)
            pdf.setLineWidth(1.8)
            p = pdf.beginPath()
            p.moveTo(cx - 6, cy - 1)
            p.lineTo(cx - 2, cy - 5)
            p.lineTo(cx + 6, cy + 5)
            pdf.drawPath(p, fill=0, stroke=1)

        def draw_line_value(y, value_text):
            value_x = 244
            pdf.setFont(fonts["regular"], 10)
            pdf.drawString(value_x - 12, y, ":")
            pdf.line(value_x, y - 2, right, y - 2)
            if value_text:
                pdf.setFillColor(colors.black)
                pdf.setFont(fonts["regular"], 10)
                pdf.drawString(value_x + 2, y, value_text)

        def draw_member_line(y, label_main, label_sub, value_text):
            pdf.setFillColor(colors.black)
            if label_main:
                pdf.setFont(fonts["regular"], 10)
                pdf.drawString(left + 6, y, "-")
                pdf.drawString(left + 18, y, label_main)
            if label_sub:
                pdf.setFont(fonts["italic"], 9)
                pdf.drawString(left + 18, y - 12, label_sub)
            draw_line_value(y, value_text or "")

        draw_header()

        pdf.setFillColor(colors.black)
        pdf.setFont(fonts["bold"], 18)
        pdf.drawCentredString(page_width / 2, page_height - 180, page7["title"])

        pdf.setFont(fonts["bold"], 18)
        pdf.drawCentredString(page_width / 2, page_height - 240, "TEST RECORD:")
        y = draw_wrapped_center(page7["object_label"], page_height - 262, 330, fonts["regular"], 17, 19)

        label_x = left
        value_x = left + 170
        label_y = y - 68

        pdf.setFont(fonts["bold"], 11)
        pdf.drawString(label_x, label_y, "PROYEK/NOMOR PROYEK")
        pdf.setFont(fonts["italic"], 10)
        pdf.drawString(label_x, label_y - 12, "(Project/Project number)")
        pdf.setFont(fonts["regular"], 11)
        pdf.drawString(value_x - 14, label_y, ":")
        pdf.drawString(value_x, label_y, page7["project_number_label"])

        label_y -= 38
        pdf.setFont(fonts["bold"], 11)
        pdf.drawString(label_x, label_y, "NOMOR DOKUMEN")
        pdf.setFont(fonts["italic"], 10)
        pdf.drawString(label_x, label_y - 12, "(Document number)")
        pdf.setFont(fonts["regular"], 11)
        pdf.drawString(value_x - 14, label_y, ":")
        pdf.drawString(value_x, label_y, page7["document_number"])

        draw_footer(page7["page_number_label"])
        pdf.showPage()

        draw_header()
        pdf.setFillColor(colors.black)
        pdf.setFont(fonts["bold"], 11)
        pdf.drawString(left + 12, page_height - 122, "1. UMUM")
        pdf.setFont(fonts["italic"], 10)
        pdf.drawString(left + 66, page_height - 122, "(General)")

        intro_y = page_height - 150
        pdf.setFont(fonts["regular"], 10)
        pdf.drawString(left + 18, intro_y, "TELAH DILAKSANAKAN PENGUJIAN TERHADAP OBYEK PENGUJIAN")
        pdf.drawString(left + 18, intro_y - 16, "BERDASARKAN TEST PROCEDURE PADA:")
        pdf.setFont(fonts["italic"], 9)
        pdf.drawString(left + 18, intro_y - 32, "(The object of the test has been conducted according to the test procedure on):")

        y = intro_y - 66
        pdf.setFont(fonts["regular"], 10)
        pdf.drawString(left + 18, y, "Tanggal")
        pdf.setFont(fonts["italic"], 9)
        pdf.drawString(left + 18, y - 12, "(Date)")
        draw_line_value(y, page8["date"])

        y -= 46
        pdf.setFont(fonts["regular"], 10)
        pdf.drawString(left + 18, y, "Tempat")
        pdf.setFont(fonts["italic"], 9)
        pdf.drawString(left + 18, y - 12, "(Place)")
        draw_line_value(y, page8["place"])

        y -= 46
        pdf.setFont(fonts["regular"], 10)
        pdf.drawString(left + 18, y, "Dilaksanakan oleh")
        pdf.setFont(fonts["italic"], 9)
        pdf.drawString(left + 18, y - 12, "(Conducted by)")
        pdf.drawString(244 - 12, y, ":")

        y -= 38
        draw_member_line(y, "Ketua tim PT PAL", "(PT PAL Team leader)", page8["team_leader"])
        y -= 46
        draw_member_line(y, "Anggota", "(Member)", page8["member_1"])
        y -= 36
        draw_member_line(y, "", "", page8["member_2"])
        y -= 36
        draw_member_line(y, "", "", page8["member_3"])
        y -= 36
        draw_member_line(y, "", "", page8["member_4"])
        y -= 46
        draw_member_line(
            y,
            "Satgas %s" % (cover["project_name"] or "FRIGATE 140 M"),
            "(Delegate of %s)" % (cover["project_name"] or "Frigate 140 M"),
            page8["delegate_name"],
        )
        if self.template_tptr == "davits_rhib":
            y -= 46
            draw_member_line(y, "Biro klasifikasi %s" % (self.kelas_kapal or "LR"), "(LR Class Surveyor)", page8["class_surveyor_name"])

        draw_footer(page8["page_number_label"])

        # PAGE 3: OBYEK PENGUJIAN & PERALATAN YANG DIGUNAKAN
        pdf.showPage()
        draw_header()

        def draw_spec_row(y, label_id, label_en, val):
            pdf.setFillColor(colors.black)
            pdf.setFont(fonts["regular"], 9)
            pdf.drawString(left + 18, y, label_id)
            if label_en:
                pdf.setFont(fonts["italic"], 8)
                pdf.drawString(left + 18, y - 10, label_en)
            
            value_x = 244
            pdf.setFont(fonts["regular"], 9)
            pdf.drawString(value_x - 12, y, ":")
            if val:
                pdf.drawString(value_x + 2, y, str(val))
            pdf.setStrokeColor(colors.HexColor("#666666"))
            pdf.setLineWidth(0.5)
            pdf.line(value_x, y - 2, right, y - 2)

        if self.template_tptr == "davits_rhib":
            # --- PAGE 9: 2. OBYEK PENGUJIAN & 3. PERALATAN YANG DIGUNAKAN ---
            pdf.setFillColor(colors.black)
            pdf.setFont(fonts["bold"], 11)
            pdf.drawString(left + 12, page_height - 122, "2. OBYEK PENGUJIAN")
            pdf.setFont(fonts["italic"], 10)
            pdf.drawString(left + 144, page_height - 122, "(Test Object)")

            y = page_height - 146
            pdf.setFont(fonts["regular"], 9)
            pdf.drawString(left + 18, y, "-  SPESIFIKASI TEKNIS DAVIT.")
            pdf.setFont(fonts["italic"], 8)
            pdf.drawString(left + 28, y - 10, "(The technical specification of Davit).")
            y -= 26
            
            draw_spec_row(y, "PEMBUAT", "(Maker)", self.davit_maker)
            y -= 20
            draw_spec_row(y, "MODEL", "(Model)", self.davit_model)
            y -= 20
            draw_spec_row(y, "TYPE", "(Type)", self.davit_type)
            y -= 20
            draw_spec_row(y, "KECEPATAN ANGKAT", "(Hoisting Speed)", self.davit_hoisting_speed)
            y -= 20
            draw_spec_row(y, "KETINGGIAN ANGKAT", "(Lifting Height)", self.davit_lifting_height)
            y -= 20
            draw_spec_row(y, "SAFETY WEIGHT LOAD (SWL)", "(SWL)", self.davit_swl)
            y -= 20
            draw_spec_row(y, "JUMLAH", "(Number)", self.davit_number)
            y -= 26

            # 3. PERALATAN YANG DIGUNAKAN (Equipment to be Used)
            pdf.setFillColor(colors.black)
            pdf.setFont(fonts["bold"], 11)
            pdf.drawString(left + 12, y, "3. PERALATAN YANG DIGUNAKAN")
            pdf.setFont(fonts["italic"], 10)
            pdf.drawString(left + 214, y, "(Equipment to be Used)")
            y -= 18

            def draw_equipment_bullet(y, label_id, label_en):
                pdf.setFillColor(colors.black)
                pdf.setFont(fonts["regular"], 9)
                pdf.drawString(left + 18, y, "-  %s" % label_id)
                pdf.setFont(fonts["italic"], 8)
                pdf.drawString(left + 28, y - 10, label_en)

            for equip in self._get_peralatan_list():
                draw_equipment_bullet(y, equip.name_id or "", equip.name_en or "")
                y -= 22
            y -= 8

            draw_footer("9 / 12")

            # --- PAGE 10: 4. PERSIAPAN SEBELUM PENGUJIAN & 5. HASIL PENGUJIAN DAVITS (a, b, c) ---
            pdf.showPage()
            draw_header()

            table_right = right
            table_width = 110
            col_width = table_width / 2
            table_left = table_right - table_width

            pdf.setFillColor(colors.black)
            pdf.setFont(fonts["bold"], 11)
            pdf.drawString(left + 12, page_height - 122, "4. PERSIAPAN SEBELUM PENGUJIAN")
            pdf.setFont(fonts["italic"], 10)
            pdf.drawString(left + 226, page_height - 122, "(Preparation Before the Test)")

            y = page_height - 144
            pdf.setStrokeColor(colors.black)
            pdf.setLineWidth(1)
            pdf.rect(table_left, y, col_width, 16)
            pdf.rect(table_left + col_width, y, col_width, 16)
            pdf.setFont(fonts["bold"], 8)
            pdf.drawCentredString(table_left + (col_width/2), y + 4, "OK")
            pdf.drawCentredString(table_left + col_width + (col_width/2), y + 4, "NOT OK")

            def draw_davit_prep_row(y, label_id, label_en, status):
                pdf.setFillColor(colors.black)
                max_text_width = table_left - left - 45
                
                lines_id = simpleSplit(label_id, fonts["regular"], 8.5, max_text_width)
                lines_en = simpleSplit(label_en, fonts["italic"], 7.5, max_text_width)
                
                text_height = len(lines_id) * 11 + len(lines_en) * 10
                box_height = 24
                row_height = max(text_height, box_height) + 10
                
                curr_y = y - 4
                
                pdf.setFont(fonts["regular"], 8.5)
                pdf.drawString(left + 18, curr_y, "-")
                
                for line in lines_id:
                    pdf.drawString(left + 30, curr_y, line)
                    curr_y -= 11
                    
                pdf.setFont(fonts["italic"], 7.5)
                for line in lines_en:
                    pdf.drawString(left + 30, curr_y, line)
                    curr_y -= 10
                
                box_y = y - (row_height + box_height) / 2
                pdf.setStrokeColor(colors.black)
                pdf.setLineWidth(0.8)
                pdf.rect(table_left, box_y, col_width, box_height)
                pdf.rect(table_left + col_width, box_y, col_width, box_height)
                
                if status == 'ok':
                    draw_checkmark(table_left + (col_width / 2), box_y + (box_height / 2))
                elif status == 'not_ok':
                    draw_checkmark(table_left + col_width + (col_width / 2), box_y + (box_height / 2))
                
                return y - row_height

            y -= 18
            y = draw_davit_prep_row(y, 
                              "INSPEKTUR QUALITY ASSURANCE PT PAL MELAPORKAN KESIAPAN DARI PERALATAN DAVITS.",
                              "(Quality assurance inspector of PT PAL reports on the readiness of the Davits equipment's)",
                              self.prep_davit_inspector)
            
            y = draw_davit_prep_row(y - 6, 
                              "KEHADIRAN TIM PENGUJIAN.",
                              "(Attendance of test team.)",
                              self.prep_davit_attendance)
            
            y = draw_davit_prep_row(y - 6, 
                              "DOKUMEN PENDUKUNG SESUAI ITEM NO. 3 PADA TEST PROSEDUR TELAH TERSEDIA.",
                              "(Document for the test according to item no. 3 in the test procedure are available.)",
                              self.prep_davit_document)

            y = draw_davit_prep_row(y - 6, 
                              "PERALATAN YANG DIGUNAKAN SESUAI ITEM NO. 3 PADA TEST RECORD TELAH TERSEDIA.",
                              "(Equipment to be used according to item no. 3 in the test record are available.)",
                              self.prep_davit_equipment)

            # Draw CATATAN (Note)
            y -= 4
            pdf.setFillColor(colors.black)
            pdf.setFont(fonts["bold"], 8)
            pdf.drawString(left + 18, y, 'CATATAN (Note): BERI TANDA "v" DIKOLOM OK (JIKA SESUAI) DAN NOT OK (JIKA TIDAK SESUAI).')
            pdf.setFont(fonts["italic"], 7)
            pdf.drawString(left + 90, y - 9, '(Please put mark "v" on column OK (if confirm) and NOT OK (if not confirm).)')
            y -= 22

            # Section 5. HASIL PENGUJIAN DAVITS
            pdf.setFillColor(colors.black)
            pdf.setFont(fonts["bold"], 11)
            pdf.drawString(left + 12, y, "5. HASIL PENGUJIAN DAVITS")
            pdf.setFont(fonts["italic"], 10)
            pdf.drawString(left + 182, y, "(Davit Test Results)")
            y -= 20

            # 5. a. Uji Beban
            pdf.setFont(fonts["bold"], 9.5)
            pdf.drawString(left + 18, y, "a. UJI BEBAN (LOAD TEST)")
            y -= 14

            y = draw_davit_prep_row(y, 
                              "UJI BEBAN STATIS / DINAMIS DAVIT.",
                              "(Static / dynamic load test of Davits.)",
                              self.davit_test_load)

            # 5. b. Uji Fungsi
            y -= 6
            pdf.setFillColor(colors.black)
            pdf.setFont(fonts["bold"], 9.5)
            pdf.drawString(left + 18, y, "b. UJI FUNGSI (FUNCTION TEST)")
            y -= 14

            y = draw_davit_prep_row(y, 
                              "UJI FUNGSI ANGKAT BEBAN (LIFTING TEST).",
                              "(Lifting load function test.)",
                              self.davit_test_lifting)
            y = draw_davit_prep_row(y - 6, 
                              "UJI FUNGSI TURUN BEBAN (LOWERING TEST).",
                              "(Lowering load function test.)",
                              self.davit_test_lowering)

            # 5. c. Pengujian Waktu Pengangkatan (Table of Hoisting Times)
            y -= 6
            pdf.setFillColor(colors.black)
            pdf.setFont(fonts["bold"], 9.5)
            pdf.drawString(left + 18, y, "c. PENGUJIAN WAKTU PENGANGKATAN DAN PENURUNAN")
            pdf.setFont(fonts["italic"], 8.5)
            pdf.drawString(left + 310, y, "(Hoisting / Lowering Time Test)")
            y -= 16

            w_desc = right - left - 180 - 18
            w_time = 90
            w_press = 90
            t_left = left + 18
            
            pdf.setStrokeColor(colors.black)
            pdf.setLineWidth(0.8)
            pdf.rect(t_left, y - 56, right - t_left, 56) 
            
            pdf.line(t_left + w_desc, y, t_left + w_desc, y - 56)
            pdf.line(t_left + w_desc + w_time, y, t_left + w_desc + w_time, y - 56)
            
            pdf.line(t_left, y - 20, right, y - 20)
            pdf.line(t_left, y - 38, right, y - 38)
            
            pdf.setFont(fonts["bold"], 8)
            pdf.drawString(t_left + 8, y - 14, "Uraian Pengujian")
            pdf.setFont(fonts["italic"], 7.5)
            pdf.drawString(t_left + 88, y - 14, "(Test Description)")
            
            pdf.setFont(fonts["bold"], 8)
            pdf.drawCentredString(t_left + w_desc + (w_time/2), y - 9, "Waktu")
            pdf.setFont(fonts["italic"], 7.5)
            pdf.drawCentredString(t_left + w_desc + (w_time/2), y - 17, "(menit / minute)")
            
            pdf.drawCentredString(t_left + w_desc + w_time + (w_press/2), y - 9, "Tekanan")
            pdf.drawCentredString(t_left + w_desc + w_time + (w_press/2), y - 17, "(kg/cm2)")

            pdf.setFillColor(colors.black)
            pdf.setFont(fonts["regular"], 8)
            pdf.drawString(t_left + 8, y - 29, "-  Waktu Pengangkatan Sekoci")
            pdf.setFont(fonts["italic"], 7.5)
            pdf.drawString(t_left + 138, y - 29, "(Lifting time of boat)")
            
            pdf.setFont(fonts["regular"], 9)
            pdf.drawCentredString(t_left + w_desc + (w_time/2), y - 32, str(self.davit_hoist_time_lift or "-"))
            pdf.drawCentredString(t_left + w_desc + w_time + (w_press/2), y - 32, str(self.davit_hoist_press_lift or "-"))

            pdf.setFont(fonts["regular"], 8)
            pdf.drawString(t_left + 8, y - 47, "-  Waktu Penurunan Sekoci")
            pdf.setFont(fonts["italic"], 7.5)
            pdf.drawString(t_left + 130, y - 47, "(Lowering time of boat)")
            
            pdf.setFont(fonts["regular"], 9)
            pdf.drawCentredString(t_left + w_desc + (w_time/2), y - 50, str(self.davit_hoist_time_lower or "-"))
            pdf.drawCentredString(t_left + w_desc + w_time + (w_press/2), y - 50, str(self.davit_hoist_press_lower or "-"))

            draw_footer("10 / 12")

            # --- PAGE 11: 5. d. PENGETESAN PERALATAN KESELAMATAN & ELEMEN DI PANEL OPERASI ---
            pdf.showPage()
            draw_header()

            pdf.setFillColor(colors.black)
            pdf.setFont(fonts["bold"], 9.5)
            pdf.drawString(left + 18, page_height - 122, "d. PENGETESAN PERALATAN KESELAMATAN (SAFETY DEVICE TEST)")
            
            y = page_height - 144
            pdf.setStrokeColor(colors.black)
            pdf.setLineWidth(1)
            pdf.rect(table_left, y, col_width, 16)
            pdf.rect(table_left + col_width, y, col_width, 16)
            pdf.setFont(fonts["bold"], 8)
            pdf.drawCentredString(table_left + (col_width/2), y + 4, "OK")
            pdf.drawCentredString(table_left + col_width + (col_width/2), y + 4, "NOT OK")

            y -= 18
            y = draw_davit_prep_row(y,
                                   "KATUP PELEPAS TEKANAN (PRESSURE RELIEF VALVE) PADA PANEL UTAMA SISTEM HIDROLIK DI-SET SESUAI SPESIFIKASI.",
                                   "(Pressure relief valve on hydraulic system main panel is set according to specification.)",
                                   self.davit_safe_relief_valve)
            
            y = draw_davit_prep_row(y - 6,
                                   "SISTEM PENGUNCIAN MEKANIS SILINDER DAVIT (CYLINDER MECHANICAL LOCKING SYSTEM) BEKERJA BAIK.",
                                   "(Davit cylinder mechanical locking system works properly.)",
                                   self.davit_safe_locking)
            
            y = draw_davit_prep_row(y - 6,
                                   "KATUP PENAHAN BEBAN (LOAD HOLDING VALVE / COUNTERBALANCE VALVE) BERFUNGSI MENCEGAH BEBAN JATUH.",
                                   "(Load holding valve / counterbalance valve functions to prevent load drop.)",
                                   self.davit_safe_holding_valve)
            
            y = draw_davit_prep_row(y - 6,
                                   "HOOK STOP LIMIT ATAS / LIMIT SWITCH MEMBATASI GERAKAN MAKSIMUM ANGKAT DENGAN AMAN.",
                                   "(Top hook stop limit / limit switch limits maximum hoist motion safely.)",
                                   self.davit_safe_stop_limit)
            
            y = draw_davit_prep_row(y - 6,
                                   "REM PENGAMAN BEKERJA KETIKA DAYA LISTRIK TIBA-TIBA MATI (POWER FAILURE BRAKE SAFELY APPLIED).",
                                   "(Safety brake operates when power supply is suddenly cut off.)",
                                   self.davit_safe_power_fail_brake)
            
            y = draw_davit_prep_row(y - 6,
                                   "PEMANAS MOTOR & TERMOSTAT (SPACE HEATER & THERMOSTAT) DI PANEL OPERASI BERFUNGSI BAIK.",
                                   "(Motor space heater & thermostat in operation panel functions properly.)",
                                   self.davit_safe_space_heater)

            # Elemen di Panel Operasi
            y -= 12
            pdf.setFillColor(colors.black)
            pdf.setFont(fonts["bold"], 9.5)
            pdf.drawString(left + 18, y, "ELEMEN DI PANEL OPERASI (ALARM & INDICATION)")
            
            y -= 22
            pdf.setStrokeColor(colors.black)
            pdf.setLineWidth(1)
            pdf.rect(table_left, y, col_width, 16)
            pdf.rect(table_left + col_width, y, col_width, 16)
            pdf.setFont(fonts["bold"], 8)
            pdf.drawCentredString(table_left + (col_width/2), y + 4, "OK")
            pdf.drawCentredString(table_left + col_width + (col_width/2), y + 4, "NOT OK")

            y -= 18
            y = draw_davit_prep_row(y,
                                   "ALARM SUARA & VISUAL (AUDIBLE & VISUAL ALARM) BERFUNGSI SAAT TERJADI ABNORMALITAS ATAU PENGOPERASIAN.",
                                   "(Audible & visual alarm functions during abnormality or operation.)",
                                   self.davit_panel_alarm)
            
            y = draw_davit_prep_row(y - 6,
                                   "INDIKASI REMOTE & POMPA (REMOTE STATUS & PUMP RUNNING INDICATION) MENUNJUKKAN STATUS AKTIF DENGAN BENAR.",
                                   "(Remote status & pump running indication correctly shows active status.)",
                                   self.davit_panel_integration)

            # Draw CATATAN (Note) on Page 11
            y -= 8
            pdf.setFillColor(colors.black)
            pdf.setFont(fonts["bold"], 8)
            pdf.drawString(left + 18, y, 'CATATAN (Note): BERI TANDA "v" DIKOLOM OK (JIKA SESUAI) DAN NOT OK (JIKA TIDAK SESUAI).')
            pdf.setFont(fonts["italic"], 7)
            pdf.drawString(left + 90, y - 9, '(Please put mark "v" on column OK (if confirm) and NOT OK (if not confirm).)')

            draw_footer("11 / 12")

            # PAGE 12: 6. CATATAN (Remark)
            pdf.showPage()
            draw_header()

            pdf.setFillColor(colors.black)
            pdf.setFont(fonts["bold"], 11)
            pdf.drawString(left + 12, page_height - 122, "6. CATATAN")
            pdf.setFont(fonts["italic"], 10)
            pdf.drawString(left + 12 + pdfmetrics.stringWidth("6. CATATAN ", fonts["bold"], 11), page_height - 122, "(Remark)")

            table_top = page_height - 138
            header_height = 24
            row_height = 20
            num_rows = 29
            table_bottom = table_top - header_height - (num_rows * row_height)
            col1_w = 385
            col2_w = (right - left) - col1_w

            # Draw Table Outer Rectangle and Vertical Grid Lines
            pdf.setStrokeColor(colors.black)
            pdf.setLineWidth(1)
            pdf.rect(left, table_bottom, right - left, table_top - table_bottom)
            
            # Vertical divider between Column 1 and Column 2
            pdf.line(left + col1_w, table_top, left + col1_w, table_bottom)

            # Draw Table Header horizontal line
            pdf.line(left, table_top - header_height, right, table_top - header_height)

            # Draw Table Header Text
            pdf.setFillColor(colors.black)
            pdf.setFont(fonts["bold"], 9)
            pdf.drawCentredString(left + (col1_w / 2), table_top - 10, "CATATAN")
            pdf.setFont(fonts["italic"], 8)
            pdf.drawCentredString(left + (col1_w / 2), table_top - 20, "(Remark)")

            pdf.setFont(fonts["bold"], 9)
            pdf.drawCentredString(left + col1_w + (col2_w / 2), table_top - 10, "AKSI")
            pdf.setFont(fonts["italic"], 8)
            pdf.drawCentredString(left + col1_w + (col2_w / 2), table_top - 20, "(Action)")

            # Fetch Catatan list
            catatan_records = self._get_catatan_list()
            
            # Set line width for inner horizontal lines
            pdf.setStrokeColor(colors.black)
            pdf.setLineWidth(0.6)
            
            for idx in range(num_rows):
                row_y = table_top - header_height - (idx * row_height)
                row_bottom = row_y - row_height
                
                # Draw horizontal line separating this row from the next
                if idx < num_rows - 1:
                    pdf.line(left, row_bottom, right, row_bottom)
                
                # Check if there is data for this row
                if idx < len(catatan_records):
                    record = catatan_records[idx]
                    remark_text = record.remark or ""
                    action_text = record.action or ""
                    
                    # Draw text inside the row
                    pdf.setFont(fonts["regular"], 8.5)
                    if remark_text:
                        pdf.drawString(left + 6, row_bottom + 6, remark_text)
                    if action_text:
                        pdf.drawString(left + col1_w + 6, row_bottom + 6, action_text)

            draw_footer("12 / 12")


        else:
            # RHIB template splits sections across multiple pages
            
            # --- PAGE 9 (overall page 10): 2. OBYEK PENGUJIAN ---
            pdf.setFillColor(colors.black)
            pdf.setFont(fonts["bold"], 11)
            pdf.drawString(left + 12, page_height - 122, "2. OBYEK PENGUJIAN")
            pdf.setFont(fonts["italic"], 10)
            pdf.drawString(left + 144, page_height - 122, "(Test Object)")

            y = page_height - 146
            pdf.setFont(fonts["regular"], 9)
            pdf.drawString(left + 18, y, "-  SPESIFIKASI TEKNIS RIGID HULL INFLATABLE BOAT (RHIB).")
            pdf.setFont(fonts["italic"], 8)
            pdf.drawString(left + 28, y - 10, "(The technical specification of Rigid Hull Inflatable Boat (RHIB)).")
            y -= 26
            
            draw_spec_row(y, "PEMBUAT", "(Maker)", self.rhib_maker)
            y -= 20
            draw_spec_row(y, "PANJANG", "(Length overall) LOA", self.rhib_loa)
            y -= 20
            draw_spec_row(y, "PANJANG LAMBUNG", "(L Hull)", self.rhib_hull_length)
            y -= 20
            draw_spec_row(y, "LEBAR", "(Breadth) B Moulded", self.rhib_breadth)
            y -= 20
            draw_spec_row(y, "TINGGI LAMBUNG", "(Height hull) H", self.rhib_hull_height)
            y -= 20
            draw_spec_row(y, "SERAT", "(Draft) T", self.rhib_draft)
            y -= 20
            draw_spec_row(y, "MESIN", "(Engine)", self.rhib_engine)
            y -= 20
            draw_spec_row(y, "JUMLAH", "(Number)", self.rhib_number)
            y -= 20
            draw_spec_row(y, "KECEPATAN MAKSIMUM", "(Max. speed)", self.rhib_max_speed)
            y -= 20
            draw_spec_row(y, "KECEPATAN BERLAYAR", "(Cruising speed)", self.rhib_cruising_speed)
            y -= 20
            draw_spec_row(y, "KAPASITAS", "(Capacity)", self.rhib_capacity)
            y -= 20
            draw_spec_row(y, "BERAT SEKOCI", "(Weight of boat)", self.rhib_boat_weight)
            y -= 20
            draw_spec_row(y, "BERAT TOTAL", "(Weight total)", self.rhib_total_weight)
            y -= 20
            draw_spec_row(y, "ASUMSI PENUMPANG 12 ORANG", "(Assuming 12 persons)", self.rhib_assumed_weight)
            y -= 20
            draw_spec_row(y, "JUMLAH", "(Number)", self.rhib_unit_count)

            draw_footer("11 / 16")

            # --- PAGE 10 (overall page 11): 3. PERALATAN YANG DIGUNAKAN ---
            pdf.showPage()
            draw_header()

            pdf.setFillColor(colors.black)
            pdf.setFont(fonts["bold"], 11)
            pdf.drawString(left + 12, page_height - 122, "3. PERALATAN YANG DIGUNAKAN")
            pdf.setFont(fonts["italic"], 10)
            pdf.drawString(left + 214, page_height - 122, "(Equipment to be Used)")

            y = page_height - 150
            def draw_equipment_bullet(y, label_id, label_en):
                pdf.setFillColor(colors.black)
                pdf.setFont(fonts["regular"], 9.5)
                pdf.drawString(left + 18, y, "-  %s" % label_id)
                pdf.setFont(fonts["italic"], 8.5)
                pdf.drawString(left + 28, y - 11, label_en)

            for equip in self._get_peralatan_list():
                draw_equipment_bullet(y, equip.name_id or "", equip.name_en or "")
                y -= 26

            draw_footer("12 / 16")

            # --- PREPARATION TABLE DRAWER SETUP FOR RHIB ---
            table_right = right
            table_width = 110
            col_width = table_width / 2
            table_left = table_right - table_width

            def draw_rhib_prep_row(y, label_id, label_en, status):
                pdf.setFillColor(colors.black)
                max_text_width = table_left - left - 45
                
                lines_id = simpleSplit(label_id, fonts["regular"], 8.5, max_text_width)
                lines_en = simpleSplit(label_en, fonts["italic"], 7.5, max_text_width)
                
                text_height = len(lines_id) * 11 + len(lines_en) * 10
                box_height = 24
                row_height = max(text_height, box_height) + 12
                
                curr_y = y - 4
                
                pdf.setFont(fonts["regular"], 8.5)
                pdf.drawString(left + 18, curr_y, "-")
                
                for line in lines_id:
                    pdf.drawString(left + 30, curr_y, line)
                    curr_y -= 11
                    
                pdf.setFont(fonts["italic"], 7.5)
                for line in lines_en:
                    pdf.drawString(left + 30, curr_y, line)
                    curr_y -= 10
                
                box_y = y - (row_height + box_height) / 2
                pdf.setStrokeColor(colors.black)
                pdf.setLineWidth(0.8)
                pdf.rect(table_left, box_y, col_width, box_height)
                pdf.rect(table_left + col_width, box_y, col_width, box_height)
                
                if status == 'ok':
                    draw_checkmark(table_left + (col_width / 2), box_y + (box_height / 2))
                elif status == 'not_ok':
                    draw_checkmark(table_left + col_width + (col_width / 2), box_y + (box_height / 2))
                
                return y - row_height

            def draw_rhib_table_header(y):
                pdf.setFillColor(colors.black)
                pdf.setFont(fonts["bold"], 11)
                pdf.drawString(left + 12, y, "4. PERSIAPAN SEBELUM PENGUJIAN")
                pdf.setFont(fonts["italic"], 10)
                pdf.drawString(left + 226, y, "(Preparation Before the Test)")
                
                header_y = y - 22
                pdf.setStrokeColor(colors.black)
                pdf.setLineWidth(1)
                pdf.rect(table_left, header_y, col_width, 16)
                pdf.rect(table_left + col_width, header_y, col_width, 16)
                pdf.setFont(fonts["bold"], 8)
                pdf.drawCentredString(table_left + (col_width/2), header_y + 4, "OK")
                pdf.drawCentredString(table_left + col_width + (col_width/2), header_y + 4, "NOT OK")
                return header_y - 20

            # --- PAGE 11 (overall page 12): 4. PERSIAPAN SEBELUM PENGUJIAN Part 1 (Items 1-8) ---
            pdf.showPage()
            draw_header()
            
            y = draw_rhib_table_header(page_height - 122)
            
            y = draw_rhib_prep_row(y,
                                  "INSPEKTUR QUALITY ASSURANCE PT PAL MELAPORKAN KESIAPAN DARI RIGID HULL INFLATABLE BOAT (RHIB) & DAVITS.",
                                  "(Quality assurance inspector of PT PAL reports on the readiness of the Rigid Hull Inflatable Boat (RHIB) & Davits.)",
                                  self.prep_rhib_item1)
            y = draw_rhib_prep_row(y - 6,
                                  "KEHADIRAN TIM PENGUJIAN.",
                                  "(Attendance of test team.)",
                                  self.prep_rhib_item2)
            y = draw_rhib_prep_row(y - 6,
                                  "DOKUMEN PENDUKUNG SESUAI ITEM NO. 3 PADA TEST PROCEDURE TELAH TERSEDIA.",
                                  "(Document for the test according to item no. 3 in the test procedure are available.)",
                                  self.prep_rhib_item3)
            y = draw_rhib_prep_row(y - 6,
                                  "PERALATAN YANG DIGUNAKAN SESUAI ITEM NO. 3 PADA TEST RECORD TELAH TERSEDIA.",
                                  "(Equipment to be used according to item no. 3 in the test record are available.)",
                                  self.prep_rhib_item4)
            y = draw_rhib_prep_row(y - 6,
                                  "DOKUMEN HASIL PEMERIKSAAN PENGUJIAN (HPP) UNTUK RIGID HULL INFLATABLE BOAT (RHIB) & DAVITS.",
                                  "(Equipment testing results documents for Rigid Hull Inflatable Boat (RHIB) & Davits.)",
                                  self.prep_rhib_item5)
            y = draw_rhib_prep_row(y - 6,
                                  "PERIKSA KONDISI RESCUE RHIB DAN PERALATAN NAVIGASI.",
                                  "(Check condition of Rescue RHIB with the navigation equipment.)",
                                  self.prep_rhib_item6)
            y = draw_rhib_prep_row(y - 6,
                                  "PERIKSA APAKAH BAHAN BAKAR MESIN UTAMA SUDAH TERISI PENUH.",
                                  "(Check the condition outboard main engine fuel is fully charged.)",
                                  self.prep_rhib_item7)
            y = draw_rhib_prep_row(y - 6,
                                  "PERIKSA APAKAH OLI HIDROLIK SISTEM KEMUDI SUDAH TERISI PENUH.",
                                  "(Check the condition of hydraulic oil steering system is full charged.)",
                                  self.prep_rhib_item8)

            draw_footer("13 / 16")

            # --- PAGE 12 (overall page 13): 4. PERSIAPAN SEBELUM PENGUJIAN Part 2 (Items 9-20) ---
            pdf.showPage()
            draw_header()

            # No main section title here as it is a continuation, but let's draw table header
            pdf.setStrokeColor(colors.black)
            pdf.setLineWidth(1)
            header_y = page_height - 122
            pdf.rect(table_left, header_y, col_width, 16)
            pdf.rect(table_left + col_width, header_y, col_width, 16)
            pdf.setFont(fonts["bold"], 8)
            pdf.drawCentredString(table_left + (col_width/2), header_y + 4, "OK")
            pdf.drawCentredString(table_left + col_width + (col_width/2), header_y + 4, "NOT OK")

            y = header_y - 20
            y = draw_rhib_prep_row(y,
                                  "MENIMBANG RESCUE RHIB SEBELUM UJI COBA LAUT. BERAT RESCUE RHIB HARUS DALAM KONDISI BEBAN PENUH.",
                                  "(Considering the Rescue RHIB before sea trial. Weight the Rescue RHIB should be in full load condition.)",
                                  self.prep_rhib_item9)
            y = draw_rhib_prep_row(y - 3, "PERALATAN KESELAMATAN.", "(Safety equipment.)", self.prep_rhib_item10)
            y = draw_rhib_prep_row(y - 3, "BAJU PENOLONG.", "(Life jacket.)", self.prep_rhib_item11)
            y = draw_rhib_prep_row(y - 3, "TANGGA BONGKAR PASANG.", "(Portable ladder.)", self.prep_rhib_item12)
            y = draw_rhib_prep_row(y - 3, "PERALATAN TALI TAMBAT.", "(Mooring rope.)", self.prep_rhib_item13)
            y = draw_rhib_prep_row(y - 3, "DAMPRA.", "(Fender.)", self.prep_rhib_item14)
            y = draw_rhib_prep_row(y - 3, "DAYUNG.", "(Paddle.)", self.prep_rhib_item15)
            y = draw_rhib_prep_row(y - 3, "PEMADAM API JINJING.", "(Portable fire extinguisher.)", self.prep_rhib_item16)
            y = draw_rhib_prep_row(y - 3, "PROSEDUR KESELAMATAN.", "(Check for continuity of the wires.)", self.prep_rhib_item17)
            y = draw_rhib_prep_row(y - 3,
                                  "MEMERIKSA URUTAN PEMASANGAN KABEL DARI SISTEM ELEKTRONIK.",
                                  "(Inspecting the cable installation sequence of the electronic system.)",
                                  self.prep_rhib_item18)
            y = draw_rhib_prep_row(y - 3,
                                  "PERALATAN TALI TAMBAT DIGUNAKAN PADA SAAT KAPAL AKAN DAN SAAT SANDAR, DIIKATKAN PADA BORDER DERMAGA.",
                                  "(The mooring equipment is used when the ship will and when it is docked, tied to the dock border.)",
                                  self.prep_rhib_item19)
            y = draw_rhib_prep_row(y - 3,
                                  "UNTUK TURUN KE KAPAL DAN NAIK DARI KAPAL KE DERMAGA, GUNAKAN TANGGA BONGKAR PASANG.",
                                  "(To get off the ship and ride from the ship to the dock, use the portable ladder.)",
                                  self.prep_rhib_item20)

            draw_footer("14 / 16")

            # --- PAGE 13 (overall page 14): 4. PERSIAPAN SEBELUM PENGUJIAN Part 3 (Items 21-22 + Note) ---
            pdf.showPage()
            draw_header()

            # Again, table header for continuation
            pdf.setStrokeColor(colors.black)
            pdf.setLineWidth(1)
            header_y = page_height - 122
            pdf.rect(table_left, header_y, col_width, 16)
            pdf.rect(table_left + col_width, header_y, col_width, 16)
            pdf.setFont(fonts["bold"], 8)
            pdf.drawCentredString(table_left + (col_width/2), header_y + 4, "OK")
            pdf.drawCentredString(table_left + col_width + (col_width/2), header_y + 4, "NOT OK")

            y = header_y - 20
            y = draw_rhib_prep_row(y,
                                  "APABILA TERJADI KEBAKARAN, SEGERA PADAMKAN DENGAN MENGGUNAKAN PEMADAM API JINJING.",
                                  "(In case of a fire, immediately turn off using a portable fire extinguisher.)",
                                  self.prep_rhib_item21)
            y = draw_rhib_prep_row(y - 12,
                                  "APABILA MESIN PENGGERAK MATI, GUNAKAN DAYUNG UNTUK MENUJU KE DERMAGA TERDEKAT DAN ALAT BANTU RADIO KOMUNIKASI UNTUK MEMINTA BANTUAN.",
                                  "(When the drive engine is off, use the paddle to get to the nearest dock and radio communication aids to ask for help.)",
                                  self.prep_rhib_item22)

            # Draw CATATAN (Note) at bottom
            y -= 40
            pdf.setFillColor(colors.black)
            pdf.setFont(fonts["bold"], 8.5)
            pdf.drawString(left + 18, y, 'CATATAN (Note): BERI TANDA "v" DIKOLOM OK (JIKA SESUAI) DAN NOT OK (JIKA TIDAK SESUAI).')
            pdf.setFont(fonts["italic"], 7.5)
            pdf.drawString(left + 90, y - 11, '(Please put mark "v" on column OK (if confirm) and NOT OK (if not confirm).)')

            draw_footer("15 / 16")

            # PAGE 16: 6. CATATAN (Remark)
            pdf.showPage()
            draw_header()

            pdf.setFillColor(colors.black)
            pdf.setFont(fonts["bold"], 11)
            pdf.drawString(left + 12, page_height - 122, "6. CATATAN")
            pdf.setFont(fonts["italic"], 10)
            pdf.drawString(left + 12 + pdfmetrics.stringWidth("6. CATATAN ", fonts["bold"], 11), page_height - 122, "(Remark)")

            table_top = page_height - 138
            header_height = 24
            row_height = 20
            num_rows = 29
            table_bottom = table_top - header_height - (num_rows * row_height)
            col1_w = 385
            col2_w = (right - left) - col1_w

            # Draw Table Outer Rectangle and Vertical Grid Lines
            pdf.setStrokeColor(colors.black)
            pdf.setLineWidth(1)
            pdf.rect(left, table_bottom, right - left, table_top - table_bottom)
            
            # Vertical divider between Column 1 and Column 2
            pdf.line(left + col1_w, table_top, left + col1_w, table_bottom)

            # Draw Table Header horizontal line
            pdf.line(left, table_top - header_height, right, table_top - header_height)

            # Draw Table Header Text
            pdf.setFillColor(colors.black)
            pdf.setFont(fonts["bold"], 9)
            pdf.drawCentredString(left + (col1_w / 2), table_top - 10, "CATATAN")
            pdf.setFont(fonts["italic"], 8)
            pdf.drawCentredString(left + (col1_w / 2), table_top - 20, "(Remark)")

            pdf.setFont(fonts["bold"], 9)
            pdf.drawCentredString(left + col1_w + (col2_w / 2), table_top - 10, "AKSI")
            pdf.setFont(fonts["italic"], 8)
            pdf.drawCentredString(left + col1_w + (col2_w / 2), table_top - 20, "(Action)")

            # Fetch Catatan list
            catatan_records = self._get_catatan_list()
            
            # Set line width for inner horizontal lines
            pdf.setStrokeColor(colors.black)
            pdf.setLineWidth(0.6)
            
            for idx in range(num_rows):
                row_y = table_top - header_height - (idx * row_height)
                row_bottom = row_y - row_height
                
                # Draw horizontal line separating this row from the next
                if idx < num_rows - 1:
                    pdf.line(left, row_bottom, right, row_bottom)
                
                # Check if there is data for this row
                if idx < len(catatan_records):
                    record = catatan_records[idx]
                    remark_text = record.remark or ""
                    action_text = record.action or ""
                    
                    # Draw text inside the row
                    pdf.setFont(fonts["regular"], 8.5)
                    if remark_text:
                        pdf.drawString(left + 6, row_bottom + 6, remark_text)
                    if action_text:
                        pdf.drawString(left + col1_w + 6, row_bottom + 6, action_text)

            draw_footer("16 / 16")

        pdf.save()
        pdf_content = buffer.getvalue()
        buffer.close()
        if not pdf_content:
            raise UserError("Halaman test record lokal tidak menghasilkan konten PDF.")
        return pdf_content

    def _get_tptr_test_record_intro_pdf(self):
        self.ensure_one()
        try:
            base_url, report_unit, username, password = self._get_jasper_test_record_config()
            if report_unit:
                test_pdf = self._request_jasper_pdf(
                    report_unit,
                    self._get_jasper_cover_sheet_params(),
                    base_url,
                    username,
                    password,
                )
                try:
                    page_count = len(PdfReader(BytesIO(test_pdf)).pages)
                except Exception:
                    page_count = 0
                if page_count >= 1:
                    return test_pdf
                raise UserError("Report test record Jasper hanya %s halaman." % page_count)
        except Exception as exc:
            _logger.warning(
                "Halaman test record Jasper gagal untuk %s, fallback ke lokal: %s",
                self.display_name,
                exc,
            )
        return self._build_local_tptr_test_record_intro_pdf()

    def _build_local_tptr_body_pdf(self):
        self.ensure_one()
        body = self._get_body_sheet_data()
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        page_width, page_height = A4
        left = 42
        right = page_width - 42
        fonts = self._get_reportlab_font_names()

        def draw_wrapped_block(text, x, start_y, width, font_name="Helvetica", font_size=9, leading=11):
            lines = simpleSplit(text or "-", font_name, font_size, width)
            text_obj = pdf.beginText(x, start_y)
            text_obj.setFont(font_name, font_size)
            text_obj.setLeading(leading)
            for line in lines:
                text_obj.textLine(line)
            pdf.drawText(text_obj)
            return start_y - (len(lines) * leading)

        def draw_common_header():
            y = page_height - 72
            pdf.setStrokeColor(colors.HexColor("#666666"))
            pdf.setFillColor(colors.HexColor("#666666"))
            pdf.setLineWidth(0.8)
            pdf.line(left, y, right, y)
            pdf.setFont(fonts["bold"], 9)
            pdf.drawString(left, y + 10, "DIVISION OF QA")
            pdf.drawString(left, y, "TEST PROCEDURE")
            pdf.setFont(fonts["regular"], 9)
            pdf.drawRightString(right, y + 3, body["project_name"])
            return y - 42

        def draw_common_footer(page_number_label):
            footer_y = 52
            pdf.setStrokeColor(colors.HexColor("#666666"))
            pdf.setLineWidth(0.8)
            pdf.line(left, footer_y + 10, right, footer_y + 10)
            pdf.setFillColor(colors.HexColor("#666666"))
            pdf.setFont(fonts["regular"], 7)
            pdf.drawString(left, footer_y, body["summary_footer_label"])
            pdf.drawRightString(right, footer_y, page_number_label)

        def draw_centered_rich_text(y, main_text, sub_text):
            gap = 3
            main_width = pdfmetrics.stringWidth(main_text, fonts["bold"], 11)
            sub_label = "(%s)" % sub_text
            sub_width = pdfmetrics.stringWidth(sub_label, fonts["italic"], 11)
            start_x = (page_width - (main_width + gap + sub_width)) / 2
            pdf.setFillColor(colors.black)
            pdf.setFont(fonts["bold"], 11)
            pdf.drawString(start_x, y, main_text)
            pdf.setFont(fonts["italic"], 11)
            pdf.drawString(start_x + main_width + gap, y, sub_label)

        def draw_role_label_block(x, y, width, label_text, role_text):
            label_font = fonts["regular"]
            role_font = fonts["italic"]
            label_size = 10
            role_size = 9
            line_gap = 12

            pdf.setFillColor(colors.black)
            pdf.setFont(label_font, label_size)
            pdf.drawString(x, y, label_text)

            label_text_width = pdfmetrics.stringWidth(label_text, label_font, label_size)
            role_label = "(%s)" % role_text
            role_text_width = pdfmetrics.stringWidth(role_label, role_font, role_size)
            same_line_x = x + label_text_width + 4
            max_right = x + width

            pdf.setFont(role_font, role_size)
            if same_line_x + role_text_width <= max_right:
                pdf.drawString(same_line_x, y, role_label)
                return y - line_gap

            role_y = y - 10
            pdf.drawString(x + 12, role_y, role_label)
            return role_y - line_gap

        def draw_toc_line(y, main_text, page_label, prefix="", sub_text="", indent=0):
            start_x = left + 26 + indent
            current_x = start_x
            if prefix:
                prefix_text = "%s " % prefix
                pdf.setFont(fonts["bold"], 11)
                pdf.drawString(current_x, y, prefix_text)
                current_x += pdfmetrics.stringWidth(prefix_text, fonts["bold"], 11)

            pdf.setFont(fonts["bold"], 11)
            pdf.drawString(current_x, y, main_text)
            current_x += pdfmetrics.stringWidth(main_text, fonts["bold"], 11)

            if sub_text:
                sub_label = " (%s)" % sub_text
                pdf.setFont(fonts["italic"], 11)
                pdf.drawString(current_x, y, sub_label)
                current_x += pdfmetrics.stringWidth(sub_label, fonts["italic"], 11)

            page_width = pdfmetrics.stringWidth(page_label, fonts["regular"], 11)
            page_x = right
            dots_start = current_x + 4
            dots_end = page_x - page_width - 1
            if dots_end > dots_start:
                dot_width = pdfmetrics.stringWidth(".", fonts["regular"], 11)
                dot_count = max(int((dots_end - dots_start) / dot_width), 0)
                pdf.setFont(fonts["regular"], 11)
                pdf.drawString(dots_start, y, "." * dot_count)

            pdf.setFont(fonts["regular"], 11)
            pdf.drawRightString(page_x, y, page_label)

        def draw_left_rich_text(y, main_text, sub_text, x=None, main_size=11, sub_size=10, gap=4):
            start_x = left if x is None else x
            pdf.setFillColor(colors.black)
            pdf.setFont(fonts["bold"], main_size)
            pdf.drawString(start_x, y, main_text)
            current_x = start_x + pdfmetrics.stringWidth(main_text, fonts["bold"], main_size)
            if sub_text:
                pdf.setFont(fonts["italic"], sub_size)
                pdf.drawString(current_x + gap, y, "(%s)" % sub_text)

        def draw_label_value(y, label_main, label_sub, value_text, value_x, value_width, value_font="regular", value_size=10):
            label_x = left + 12
            pdf.setFillColor(colors.black)
            pdf.setFont(fonts["bold"], 10)
            pdf.drawString(label_x, y, label_main)
            label_end_y = y - 12
            if label_sub:
                pdf.setFont(fonts["italic"], 9)
                pdf.drawString(label_x, y - 10, "(%s)" % label_sub)
                label_end_y = y - 22
            pdf.setFont(fonts["regular"], 10)
            pdf.drawString(value_x - 12, y, ":")
            end_y = draw_wrapped_block(
                value_text or "-",
                value_x,
                y,
                value_width,
                fonts[value_font],
                value_size,
                value_size + 2,
            )
            return min(label_end_y, end_y) - 8

        def draw_signature_image(signature_value, x, y, width, height):
            if not signature_value:
                return
            try:
                signature_bytes = signature_value
                if isinstance(signature_bytes, str):
                    signature_bytes = signature_bytes.encode("utf-8")
                image_reader = ImageReader(BytesIO(base64.b64decode(signature_bytes)))
                pdf.drawImage(
                    image_reader,
                    x,
                    y,
                    width=width,
                    height=height,
                    preserveAspectRatio=True,
                    anchor="c",
                    mask="auto",
                )
            except Exception:
                return

        def draw_page6_rows(y, rows, main_size=10, sub_size=8):
            for row in rows:
                indent = int(row.get("indent") or 0)
                prefix = (row.get("prefix") or "-").strip()
                main_text = (row.get("main") or "-").strip()
                sub_text = (row.get("sub") or "").strip()
                bullet_x = left + 24 + (indent * 18)
                text_x = bullet_x + 14
                text_width = right - text_x
                pdf.setFillColor(colors.black)
                pdf.setFont(fonts["regular"], main_size)
                pdf.drawString(bullet_x, y, prefix)
                y = draw_wrapped_block(main_text, text_x, y, text_width, fonts["regular"], main_size, main_size + 2) - 2
                if sub_text:
                    y = draw_wrapped_block(sub_text, text_x, y, text_width, fonts["italic"], sub_size, sub_size + 2) - 6
                else:
                    y -= 6
            return y

        y = draw_common_header()
        pdf.setFillColor(colors.black)
        draw_centered_rich_text(y, "DISTRIBUSI", "Distributed To")
        y -= 24
        for row in body["distributed_to_rows"]:
            pdf.setFont(fonts["regular"], 10)
            pdf.drawString(left + 6, y, "-")
            y = draw_wrapped_block(row["title"], left + 18, y, right - left - 24, fonts["regular"], 10, 12)
            pdf.setFont(fonts["italic"], 9)
            y = draw_wrapped_block(row["subtitle"], left + 18, y + 1, right - left - 24, fonts["italic"], 9, 10)
            y -= 8

        pdf.setFillColor(colors.HexColor("#dfdfdf"))
        pdf.rect(left, y - 2, right - left, 12, stroke=0, fill=1)
        y -= 18

        label_width = 192
        value_x = left + label_width + 16
        value_width = right - value_x
        for row in body["role_rows"]:
            label_end_y = draw_role_label_block(left, y, label_width - 8, row["label"], row["role"])
            pdf.setFont(fonts["regular"], 10)
            pdf.drawString(left + label_width, y, ":")

            end_y = draw_wrapped_block(row["value"], value_x, y, value_width, fonts["regular"], 10, 12)
            pdf.setFont(fonts["italic"], 9)
            end_y = draw_wrapped_block(row["subtitle"], value_x, end_y + 1, value_width, fonts["italic"], 9, 10)
            y = min(label_end_y, end_y) - 14

        pdf.setFillColor(colors.HexColor("#dfdfdf"))
        pdf.rect(left, y, right - left, 12, stroke=0, fill=1)
        draw_common_footer(body["body_page_number_label"])

        pdf.showPage()

        y = draw_common_header()
        draw_centered_rich_text(y, "DAFTAR ISI", "Content")
        y -= 30
        draw_toc_line(y, "TEST PROCEDURE", "2")
        y -= 22
        for row in body["toc_test_procedure_rows"]:
            draw_toc_line(
                y,
                row["title"],
                row["page"],
                prefix=row["number"],
                sub_text=row["subtitle"],
            )
            y -= 20

        y -= 6
        draw_toc_line(y, "TEST RECORD", "7")
        y -= 22
        for row in body["toc_test_record_rows"]:
            draw_toc_line(
                y,
                row["title"],
                row["page"],
                prefix=row["number"],
                sub_text=row["subtitle"],
            )
            y -= 20

        draw_common_footer(body["toc_page_number_label"])

        pdf.showPage()

        y = draw_common_header()
        draw_left_rich_text(y, "1. PENDAHULUAN", "Introduction", left + 12, 11, 10)
        pdf.setStrokeColor(colors.HexColor("#666666"))
        pdf.line(left + 12, y - 8, right, y - 8)
        y -= 28

        intro_width = right - left - 24
        intro_paragraphs = [
            (
                "PENGUJIAN DILAKSANAKAN DI AREA SESUAI DENGAN PILIHAN DARI GALANGAN KAPAL.",
                "(The test will be performed in a suitable area at the Yard's option.)",
            ),
            (
                "KEGIATAN PENGUJIAN DI DERMAGA DILAKSANAKAN SESUAI DENGAN STANDAR PROSEDUR PENGUJIAN GALANGAN KAPAL DAN REKOMENDASI VENDOR SERTA PERSYARATAN KLASIFIKASI.",
                "(The harbor test activity will be carried out in accordance with the Yard's standard trial procedure and supplier recommendation and as required by Class.)",
            ),
        ]
        for indo_text, eng_text in intro_paragraphs:
            y = draw_wrapped_block(indo_text, left + 24, y, intro_width - 12, fonts["regular"], 10, 12) - 3
            y = draw_wrapped_block(eng_text, left + 24, y, intro_width - 12, fonts["italic"], 9, 10) - 9

        draw_left_rich_text(y, body["intro_heading_main"], body["intro_heading_sub"], left + 12, 11, 10)
        y -= 18

        label_value_x = left + 225
        label_value_width = right - label_value_x - 6
        y = draw_label_value(
            y,
            "NOMOR PROYEK",
            "Project Number",
            body["intro_project_number_label"],
            label_value_x,
            label_value_width,
        )
        y = draw_label_value(
            y,
            "PENGUJIAN UNTUK NOMOR PROYEK",
            "Test related to Project Number",
            body["intro_test_related_project_no"],
            label_value_x,
            label_value_width,
        )
        y = draw_label_value(
            y,
            "NOMOR DOKUMEN",
            "Document Number",
            body["intro_document_number"],
            label_value_x,
            label_value_width,
        )
        y = draw_label_value(
            y,
            body["intro_test_type_label"],
            "",
            body["intro_test_object_label"],
            label_value_x,
            label_value_width,
        )
        y = draw_label_value(
            y,
            "SPESIFIKASI KONTRAK",
            "Contract specification",
            body["intro_contract_specification"],
            label_value_x,
            label_value_width,
        )

        table_top = y - 6
        col_widths = [118, 110, 128, 86]
        row_height = 28
        header_height = 20
        table_height = header_height + (row_height * 2)
        table_x = left + 12
        current_x = table_x
        pdf.setStrokeColor(colors.black)
        pdf.setLineWidth(0.8)
        pdf.rect(table_x, table_top - table_height, sum(col_widths), table_height, stroke=1, fill=0)
        for width in col_widths[:-1]:
            current_x += width
            pdf.line(current_x, table_top, current_x, table_top - table_height)
        pdf.line(table_x, table_top - header_height, table_x + sum(col_widths), table_top - header_height)
        pdf.line(table_x, table_top - header_height - row_height, table_x + sum(col_widths), table_top - header_height - row_height)

        header_titles = ["Acceptance", "Name", "Signature", "Date"]
        current_x = table_x
        pdf.setFont(fonts["bold"], 9)
        for title, width in zip(header_titles, col_widths):
            pdf.drawCentredString(current_x + (width / 2), table_top - 13, title)
            current_x += width

        for index, row in enumerate(body["intro_acceptance_rows"]):
            row_top = table_top - header_height - (index * row_height)
            text_y = row_top - 16
            pdf.setFont(fonts["regular"], 9)
            pdf.drawCentredString(table_x + (col_widths[0] / 2), text_y, row["acceptance"] or "-")
            pdf.drawCentredString(table_x + col_widths[0] + (col_widths[1] / 2), text_y, row["name"] or "")
            draw_signature_image(
                row["signature_image"],
                table_x + col_widths[0] + col_widths[1] + 6,
                row_top - row_height + 4,
                col_widths[2] - 12,
                row_height - 8,
            )
            pdf.drawCentredString(table_x + sum(col_widths[:-1]) + (col_widths[3] / 2), text_y, row["date"] or "")

        y = table_top - table_height - 28
        draw_left_rich_text(y, "2. UMUM", "General", left + 12, 11, 10)
        y -= 22

        if self.template_tptr == "davits_rhib":
            umum_paragraphs = [
                (
                    "PENGUJIAN DILAKSANAKAN UNTUK MEMASTIKAN BAHWA PERALATAN DAVITS DAN RIGID HULL INFLATABLE BOAT (RHIB) BEROPERASI SECARA AMAN DAN BERFUNGSI DENGAN BAIK SELAMA PENGOPERASIANNYA.",
                    "(The test shall be carried out in order to confirm that Davits and Rigid Hull Inflatable Boat (RHIB) operates safely and well function during its operation.)",
                )
            ]
        else:
            umum_paragraphs = [
                (
                    "PENGUJIAN DILAKSANAKAN UNTUK MEMASTIKAN BAHWA RIGID HULL INFLATABLE BOAT (RHIB) BEROPERASI SECARA AMAN DAN BERFUNGSI DENGAN BAIK SELAMA PENGOPERASIANNYA.",
                    "(The test shall be carried out in order to confirm that Rigid Hull Inflatable Boat (RHIB) operates safely and well function during its operation.)",
                )
            ]
        for indo_text, eng_text in umum_paragraphs:
            y = draw_wrapped_block(indo_text, left + 24, y, intro_width - 12, fonts["regular"], 10, 12) - 3
            y = draw_wrapped_block(eng_text, left + 24, y, intro_width - 12, fonts["italic"], 9, 10) - 8

        draw_common_footer(body["intro_page_number_label"])
        pdf.showPage()

        y = draw_common_header()
        draw_left_rich_text(y, "3. DOKUMEN PENDUKUNG", "Documents for the test", left + 12, 11, 10)
        y -= 20
        y = draw_page6_rows(y, body["procedure_document_rows"], 10, 8)
        y -= 6

        draw_left_rich_text(y, "4. REFERENSI PENDUKUNG", "References for the test", left + 12, 11, 10)
        y -= 20
        y = draw_page6_rows(y, body["procedure_supporting_reference_rows"], 10, 8)
        y -= 6

        draw_left_rich_text(y, "5. KONDISI", "Condition", left + 12, 11, 10)
        y -= 20
        y = draw_page6_rows(y, body["procedure_condition_rows"], 10, 8)
        y -= 6

        draw_left_rich_text(y, "6. WAKTU", "Time", left + 12, 11, 10)
        y -= 20
        y = draw_page6_rows(y, body["procedure_time_rows"], 10, 8)
        y -= 6

        draw_left_rich_text(y, "7. DEFINISI PENGUJIAN", "Definition of the Test", left + 12, 11, 10)
        y -= 20
        y = draw_page6_rows(y, body["procedure_definition_rows"], 10, 8)

        draw_common_footer(body["procedure_page_number_label"])

        if self.template_tptr == "rhib":
            # Define bullet point helper internally for pages 7 & 8
            def draw_bullet_point(prefix, main_text, sub_text, y_coord, text_x=None):
                if text_x is None:
                    text_x = left + 40
                pdf.drawString(text_x - 12, y_coord, prefix)
                new_y = draw_wrapped_block(main_text, text_x, y_coord, right - text_x - 6, fonts["regular"], 9.5, 11.5) - 2
                if sub_text:
                    new_y = draw_wrapped_block(sub_text, text_x, new_y, right - text_x - 6, fonts["italic"], 8.5, 10) - 6
                else:
                    new_y -= 6
                return new_y

            # --- PAGE 7 OF 16 ---
            pdf.showPage()
            y = draw_common_header()
            pdf.setFillColor(colors.black)
            
            # Bullet point 1
            y = draw_bullet_point("•", "HULL TIDAK RETAK.", "(The Hull of RHIB is not cracked)", y)
            # Bullet point 2
            y = draw_bullet_point("•", "MESIN PENGGERAK BERFUNGSI BAIK.", "(The Engine driven well functions.)", y)
            # Bullet point 3
            y = draw_bullet_point("•", "PERALATAN KESELAMATAN DILENGKAPI.", "(The Safety equipment's to be complete.)", y)
            y -= 14
            
            # Section: OBSERVASI PENGUJIAN
            pdf.setFont(fonts["bold"], 10)
            pdf.drawString(left + 18, y, "-")
            y = draw_wrapped_block("OBSERVASI PENGUJIAN", left + 30, y, right - left - 36, fonts["bold"], 10, 12)
            y = draw_wrapped_block("(Test observation)", left + 30, y + 1, right - left - 36, fonts["italic"], 9, 10) - 10
            
            # Subpoint a
            y = draw_bullet_point("a.", "PENGUJIAN PERALATAN RHIB DILAKUKAN DI DARAT MAUPUN DI LAUT.", 
                                  "(The testing of RHIB equipment's is carried out on land or sea trial.)", y, text_x=left+44)
            # Subpoint b
            y = draw_bullet_point("b.", "TIDAK ADANYA PANAS PADA PENGGERAK ELEKTRIK MOTOR. PENGUJIAN START DARI ENGINE DRIVEN, IDLE, AKSELERASI, SUARA DAN GETARAN.", 
                                  "(The testing of engine driven start, idle, acceleration, sound and vibration.)", y, text_x=left+44)
            # Subpoint c
            y = draw_bullet_point("c.", "MEMERIKSA SISTEM PROPULSI NYA.", 
                                  "(The checking of propulsion system.)", y, text_x=left+44)
            y -= 14
            
            # Section: PELAKSANAAN PENGUJIAN
            pdf.setFont(fonts["bold"], 10)
            pdf.drawString(left + 18, y, "-")
            y = draw_wrapped_block("PELAKSANAAN PENGUJIAN", left + 30, y, right - left - 36, fonts["bold"], 10, 12)
            y = draw_wrapped_block("(Conducting the Tests)", left + 30, y + 1, right - left - 36, fonts["italic"], 9, 10) - 10
            
            # Subpoint a
            y = draw_bullet_point("a.", 
                                  "UJI OPERASI MESIN, TES AWAL MESIN AKAN DILAKUKAN UNTUK RESCUE RHIB DALAM KEADAAN MUATAN PENUH. START-UP DILAKASNAKAN MAKSIMAL 3 (TIGA) KALI, DIMANA SETIAP INTERVAL WAKTU TIDAK LEBIH DARI 5 DETIK, SETELAH START-UP YANG PERTAMA SUKSES, KEMUDIAN:",
                                  "(Test machine operation, the machine's initial test will be conducted for Rescue RHIB in full charge. Start-up is performed at max 3 (three) times, where each time interval is not more than 5 seconds, after successful start-up, then:)",
                                  y, text_x=left+44)
            y -= 8
            
            # Nested Bullet 1
            y = draw_bullet_point("•", "10 MENIT PERTAMA:", "(The first 10 minutes:)", y, text_x=left+62)
            y = draw_wrapped_block("JALANKAN MESIN DENGAN KECEPATAN YANG SERENDAH MUNGKIN. PALING BAIK YAITU PADA KECEPATAN TANPA BEBAN DENGAN POSISI NETRAL.", 
                                   left + 62, y, right - left - 68, fonts["regular"], 9.5, 11) - 2
            y = draw_wrapped_block("(Run the engine at the lowest possible speed. The best is at the no-load speed with a neutral position.)", 
                                   left + 62, y, right - left - 68, fonts["italic"], 8.5, 10) - 12
            
            # Nested Bullet 2
            y = draw_bullet_point("•", "50 MENIT BERIKUTNYA:", "(50 minutes later:)", y, text_x=left+62)
            
            draw_common_footer("7 / 16")
            
            # --- PAGE 8 OF 16 ---
            pdf.showPage()
            y = draw_common_header()
            pdf.setFillColor(colors.black)
            
            # Continuation text for Nested Bullet 2
            y = draw_wrapped_block("JANGAN MELAMPAUI SETENGAH AKSELERASI (KIRA-KIRA 3000 PUTARAN/MENIT). SESEKALI UBAHLAH KECEPATAN MESIN. JIKA PERAHU ANDA MUDAH MENCAPAI KESEIMBANGAN LAJU, JALANKAN PERAHU PADA AKSELERASI PENUH HINGGA MENCAPAI KESEIMBANGAN LAJU, KEMUDIAN SEGERA TURUNKAN AKSELERASINYA HINGGA 3000 PUTARAN/MENIT ATAU KURANG.", 
                                   left + 62, y, right - left - 68, fonts["regular"], 9.5, 11) - 2
            y = draw_wrapped_block("(Do not exceed half the acceleration (approximately 3000 rev/min). Occasionally change the speed of the machine. If your boat is easy to reach the balance of speed, run the boat at full acceleration until it reaches the balance of speed, then immediately lower its acceleration to 3000 rev/min or less.)", 
                                   left + 62, y, right - left - 68, fonts["italic"], 8.5, 10) - 16
            
            # Subpoint b of PELAKSANAAN PENGUJIAN
            y = draw_bullet_point("b.", 
                                  "MESIN JUGA DILENGKAPI DENGAN STARTER MANUAL, START MANUAL JUGA TIDAK LEBIH DARI 3 KALI.",
                                  "(The engine is also equipped with manual starter; manual start should be for not more than 3 times.)",
                                  y, text_x=left+44)
            y -= 6
            
            # Subpoint c
            y = draw_bullet_point("c.", 
                                  "UJI PENGUKURAN DAN KECEPATAN BERLAYAR:",
                                  "(Sailing and speed measurement test:)",
                                  y, text_x=left+44)
            y = draw_wrapped_block("PENGUJIAN PELAYARAN DAN PENGUKURAN KECEPATAN AKAN DILAKUKAN UNTUK RESCUE RHIB DENGAN KEADAAN MUATAN PENUH, UJI KECEPATAN DARI KECEPATAN 0 (NOL) HINGGA 27 KNOT DILAKUKAN SECARA BERTAHAP DAN PADA KECEPATANNYA 27 KNOT (MAKSIMUM) AKAN DITAHAN SELAMA 5 MENIT, KEMUDIAN KECEPATAN DITURUNKAN HINGGA KECEPATAN BERTAHAN 18 KNOT DAN DIATAHAN SELAMA 15 MENIT., DIMANA PADA KECEPATAN BERLAYAR 18 KNOT TERSEBUT JUGA DILAKUKAN UJI BERPUTAR DAN UJI ZIG-ZAG. UJI KECEPATAN DIUKUR DENGAN GPS, DAN KECEPATAN MAKSIMUM BERLAYAR YANG SEBENARNYA HARUS DICATAT.", 
                                   left + 44, y, right - left - 50, fonts["regular"], 9.5, 11) - 2
            y = draw_wrapped_block("(Sailing test and speed measurement will be commenced for Rescue RHIB under fully loaded situation, speed test from 0 (Zero) to 27 knots will proceed gradually and will endure the 27 knots speed for 5 minutes. Subsequently, the speed will be reduced to endurance speed of 18 knots for 15 minutes, in which on the sailing speed of 18 knots, the maneuvering test and zig-zag test will be performed. Speed test is measured with GPS, and the actual maximum speed of sailing must be recorded.)", 
                                   left + 44, y, right - left - 50, fonts["italic"], 8.5, 10) - 16
            
            # Subpoint d
            y = draw_bullet_point("d.", 
                                  "PERCOBAAN BERPUTAR DAN ZIG-ZAG.",
                                  "(Turning test and zig-zag test.)",
                                  y, text_x=left+44)
            y = draw_wrapped_block("SELAMA BERLAYAR PERCOBAAN BERPUTAR DAN ZIG-ZAG HARUS DILAKUKAN.", 
                                   left + 44, y, right - left - 50, fonts["regular"], 9.5, 11) - 2
            y = draw_wrapped_block("(During sailing, turning test and zig-zag test should be performed.)", 
                                   left + 44, y, right - left - 50, fonts["italic"], 8.5, 10) - 10
            
            draw_common_footer("8 / 16")

        pdf.save()
        pdf_content = buffer.getvalue()
        buffer.close()
        if not pdf_content:
            raise UserError("Body TPTR lokal tidak menghasilkan konten PDF.")
        return pdf_content

    def _get_tptr_body_pdf(self):
        self.ensure_one()
        try:
            return self._get_local_tptr_body_pdf()
        except Exception as exc:
            _logger.warning(
                "Body TPTR lokal gagal untuk %s, fallback ke Jasper body: %s",
                self.display_name,
                exc,
            )
        try:
            body_pdf = self._get_jasper_body_pdf()
            try:
                body_page_count = len(PdfReader(BytesIO(body_pdf)).pages)
            except Exception:
                body_page_count = 0
            if body_page_count >= 4:
                return body_pdf
            raise UserError("Body Jasper TPTR hanya %s halaman." % body_page_count)
        except Exception as exc:
            raise UserError("Body TPTR gagal dibuat: %s" % exc)

    # Cover dan body digabung agar user tetap menerima satu PDF utuh di wizard/review/download.
    def _get_jasper_combined_pdf(self):
        self.ensure_one()
        cover_pdf = self._get_jasper_cover_sheet_pdf()
        body_pdf = self._get_tptr_body_pdf()
        test_record_pdf = self._get_tptr_test_record_intro_pdf()

        merger = PdfMerger()
        merger.append(BytesIO(cover_pdf))
        merger.append(BytesIO(body_pdf))
        merger.append(BytesIO(test_record_pdf))

        output_stream = BytesIO()
        merger.write(output_stream)
        merger.close()
        return output_stream.getvalue()

    def _get_summary_document_name(self, document_name):
        self.ensure_one()
        label = " ".join(((document_name or "-").replace("\r", " ").replace("\n", " ")).split())
        normalized = label.upper()
        prefixes = (
            "TEST PROCEDURE AND TEST RECORD OF ",
            "TEST PROCEDURE AND TEST RECORD ",
            "TEST PROCEDURE OF ",
            "TEST PROCEDURE ",
            "TEST RECORD OF ",
        )
        for prefix in prefixes:
            if normalized.startswith(prefix):
                trimmed = label[len(prefix) :].strip(" :-")
                return trimmed or label
        return label

    def _get_short_footer_document_name(self, document_name):
        self.ensure_one()
        label = " ".join(((document_name or "-").replace("\r", " ").replace("\n", " ")).split())
        short_label = label.replace("RIGID HULL INFLATABLE BOAT (RHIB)", "RHIB")
        short_label = short_label.replace("RIGID HULL INFLATABLE BOAT", "RHIB")
        short_label = " ".join(short_label.split())
        return short_label or label

    def _get_body_project_number_display(self):
        self.ensure_one()
        raw_value = " ".join(((self.nomor_proyek or "-").replace("\r", " ").replace("\n", " ")).split())
        if "/" not in raw_value:
            return raw_value or "-"

        parts = [part.strip() for part in raw_value.split("/") if part.strip()]
        if len(parts) <= 1:
            return raw_value or "-"

        base_part = parts[0]
        match = re.match(r"^(.*?)(\d+)$", base_part)
        if not match:
            return ", ".join(parts)

        prefix, base_number = match.groups()
        expanded = [base_part]
        base_width = len(base_number)
        for part in parts[1:]:
            if re.fullmatch(r"\d+", part):
                normalized = part.zfill(base_width) if len(part) < base_width else part
                expanded.append("%s%s" % (prefix, normalized))
            else:
                expanded.append(part)
        return ", ".join(expanded)

    def _get_body_page5_labels(self):
        self.ensure_one()
        template_profile = self._get_tptr_template_profile(self.template_tptr)
        object_label = template_profile["drawing_document_name"]
        test_prefix = "HAT" if self.jenis_tes == "hat" else "SAT"
        test_full_label = "HARBOR ACCEPTANCE TEST" if self.jenis_tes == "hat" else "SEA ACCEPTANCE TEST"
        test_full_label_title = "Harbor Acceptance Test" if self.jenis_tes == "hat" else "Sea Acceptance Test"
        object_label_title = "Davits for RHIB" if self.template_tptr == "davits_rhib" else "Rigid Hull Inflatable Boat (RHIB)"
        return {
            "test_prefix": test_prefix,
            "test_full_label": test_full_label,
            "test_full_label_title": test_full_label_title,
            "object_label": object_label,
            "headline_main": "%s UNTUK %s" % (test_prefix, object_label),
            "headline_sub": "%s %s" % (test_full_label_title, object_label_title),
        }

    def _get_body_page6_defaults(self):
        self.ensure_one()
        reference_suffix = "DAVITS FOR RHIB" if self.template_tptr == "davits_rhib" else "RHIB"
        return {
            "supporting_reference": "Annex DD Section 4. Point 11.2 %s" % reference_suffix,
            "condition": "\n\n".join(
                [
                    "KONDISI TENANG DENGAN GELOMBANG RENDAH (<0,5 meter).\n(Calm condition with low waves at (<0,5 meters).)",
                    "TIDAK HUJAN ATAU KABUT DENGAN JARAK PANDANG MINIMAL 1 NM.\n(No rain and fog with minimal visibility 1 NM.)",
                    "LOKASI PENGUJIAN AMAN DAN JAUH DARI JALUR PELAYARAN.\n(The location of the test should be safe and far from the shipping lane.)",
                    "KONSTRUKSI DAN PERLENGKAPAN DAVIT ATAU DEREK UNTUK RHIB DALAM KONDISI BAGUS.\n(Davit and accessories for RHIB to be completed in good condition.)",
                    "KONDISI TALI KAWAT SLING DAN KONEKSINYA PADA PERALATAN ANGKAT UNTUK RHIB DALAM KONDISI BAIK.\n(The condition of wire rope and its connection on the Davit equipment in good condition.)",
                    "RHIB DAN PERLENGKAPANNYA DALAM KONDISI BAIK DAN SIAP DIOPERASIKAN.\n(RHIB and accessories to be in good condition and ready to be operated.)",
                ]
            ),
            "time": "PERKIRAAN 1 JAM.\n(Approx. 1 Hour.)",
        }

    def _parse_body_page6_rows(self, raw_value):
        self.ensure_one()
        rows = []
        current_main = ""
        current_sub_parts = []
        normalized_text = (raw_value or "").replace("\r\n", "\n").replace("\r", "\n")

        def _flush():
            nonlocal current_main, current_sub_parts
            if current_main or current_sub_parts:
                rows.append(
                    {
                        "main": (current_main or "").strip(),
                        "sub": " ".join(part.strip() for part in current_sub_parts if part.strip()).strip(),
                    }
                )
            current_main = ""
            current_sub_parts = []

        for line in normalized_text.split("\n"):
            clean_line = (line or "").strip()
            if not clean_line:
                _flush()
                continue
            if not current_main:
                current_main = clean_line
                continue
            if clean_line.startswith("("):
                current_sub_parts.append(clean_line)
                continue
            _flush()
            current_main = clean_line

        _flush()
        return [row for row in rows if row.get("main") or row.get("sub")]

    def _build_body_page6_markup(self, rows):
        self.ensure_one()
        markup_lines = []
        for row in rows:
            prefix = (row.get("prefix") or "-").strip()
            main_text = (row.get("main") or "").strip()
            sub_text = (row.get("sub") or "").strip()
            indent = "    " * int(row.get("indent") or 0)
            main_line = " ".join(part for part in [prefix, main_text] if part).strip()
            if main_line:
                markup_lines.append("%s%s" % (indent, html.escape(main_line)))
            if sub_text:
                markup_lines.append(
                    "<style isItalic='true'>%s%s</style>" % (indent, html.escape(sub_text))
                )
            markup_lines.append("")
        while markup_lines and not markup_lines[-1]:
            markup_lines.pop()
        return "<br/>".join(markup_lines) or "-"

    def _get_body_page6_static_rows(self):
        self.ensure_one()
        is_davits = self.template_tptr == "davits_rhib"
        document_rows = [
            {
                "prefix": "-",
                "main": "GAMBAR PABRIK DARI RHIB",
                "sub": "(Maker drawing of RHIB.)",
                "indent": 0,
            },
            {
                "prefix": "-",
                "main": "GAMBAR PABRIK DARI DAVIT CRANE UNTUK RHIB" if not is_davits else "GAMBAR PABRIK DARI DAVITS UNTUK RHIB",
                "sub": "(Maker drawing of RHIB Davit Crane)" if not is_davits else "(Maker drawing of Davits for RHIB)",
                "indent": 0,
            },
            {
                "prefix": "-",
                "main": "HASIL UJI PERCOBAAN DILAUT DARI RHIB",
                "sub": "(Sea Trial Test record of RHIB)",
                "indent": 0,
            },
            {
                "prefix": "-",
                "main": "DOCUMENTS OF INSPECTION OF DAVITS AND RIGID HULL INFLATABLE BOAT (RHIB) EQUIPMENT TESTING RESULT.",
                "sub": "",
                "indent": 0,
            },
        ]
        definition_rows = [
            {
                "prefix": "-",
                "main": "METODE PENGUJIAN",
                "sub": "(Test Method)",
                "indent": 0,
            },
            {
                "prefix": "a.",
                "main": (
                    "MEMERIKSA KONDISI FISIK SECARA LANGSUNG KE PERALATAN DAVITS DAN RHIB:"
                    if is_davits
                    else "MEMERIKSA KONDISI FISIK SECARA LANGSUNG KE PERALATAN RHIB:"
                ),
                "sub": (
                    "(Check the physical condition directly to Davits and RHIB equipment.)"
                    if is_davits
                    else "(Check the physical condition directly to RHIB equipment.)"
                ),
                "indent": 1,
            },
        ]
        return {
            "document_rows": document_rows,
            "definition_rows": definition_rows,
        }

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

        def _name_or_status(name_value, status_value):
            return (name_value or "").strip() or _yes_no(status_value)

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
                    "drawn_by": _name_or_status(row.drawn_by_name, row.tanda_tangan_shipyard),
                    "designed_by": _name_or_status(row.designed_by_name, row.tanda_tangan_class),
                    "checked_by": _name_or_status(row.checked_by_name, row.tanda_tangan_owner_delegate),
                    "approved_by": _name_or_status(row.approved_by_name, row.tanda_tangan_owner_delegate),
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
        template_profile = self._get_tptr_template_profile(self.template_tptr)
        drawing_name = latest_dokumen.referensi_desain or template_profile["drawing_document_name"]
        drw_no = latest_dokumen.dokumen_maker or template_profile["document_no"]
        summary_document_name = self._get_summary_document_name(drawing_name)
        test_type_label = "Harbor Acceptance Test" if self.jenis_tes == "hat" else "Sea Acceptance Test"
        project_full_label = "%s / %s" % (self.nama_kapal or "-", self.nomor_proyek or "-")
        document_footer_label = "%s- %s" % (drw_no, drawing_name)
        summary_footer_label = template_profile["footer_label"]
        approval_class_label = "%s CLASS" % (self.kelas_kapal or "-")
        approval_owner_label = self.delegasi_pemilik or "Delegate Team"
        fallback_review_date = fields.Date.to_date(latest_review.tanggal_input) if latest_review and latest_review.tanggal_input else fields.Date.context_today(self)
        drawn_by_date = latest_review.tanggal_drawn_by if latest_review and latest_review.tanggal_drawn_by else fallback_review_date
        designed_by_date = latest_review.tanggal_designed_by if latest_review and latest_review.tanggal_designed_by else fallback_review_date
        checked_by_date = latest_review.tanggal_checked_by if latest_review and latest_review.tanggal_checked_by else fallback_review_date
        approved_by_date = latest_review.tanggal_approved_by if latest_review and latest_review.tanggal_approved_by else fallback_review_date
        page_suffix = "12" if self.template_tptr == "davits_rhib" else "16"
        return {
            "year": now_dt.year,
            "project_name": self.nama_kapal or "-",
            "project_no": self.nomor_proyek or "-",
            "drawing_document_name": drawing_name,
            "summary_document_name": summary_document_name,
            "drw_document_no": drw_no,
            "template_tptr": self.template_tptr or "rhib",
            "template_tptr_label": template_profile["label"],
            "owner": self.delegasi_pemilik or "-",
            "class_name": self.kelas_kapal or "-",
            "designer": latest_lokasi.name if latest_lokasi else "-",
            "group_name": latest_lokasi.lokasi_pengujian if latest_lokasi else "-",
            "scale": "-",
            "size": "A4",
            "sheet_label": "1 of 1",
            "test_type_label": test_type_label,
            "project_full_label": project_full_label,
            "document_footer_label": document_footer_label,
            "summary_footer_label": summary_footer_label,
            "summary_page_number_label": "2 / %s" % page_suffix,
            "body_page_number_label": "3 / %s" % page_suffix,
            "toc_page_number_label": "4 / %s" % page_suffix,
            "intro_page_number_label": "5 / %s" % page_suffix,
            "procedure_page_number_label": "6 / %s" % page_suffix,
            "approval_class_label": approval_class_label,
            "approval_owner_label": approval_owner_label,
            "drawn_by_date": fields.Date.to_string(drawn_by_date) if drawn_by_date else "-",
            "designed_by_date": fields.Date.to_string(designed_by_date) if designed_by_date else "-",
            "checked_by_date": fields.Date.to_string(checked_by_date) if checked_by_date else "-",
            "approved_by_date": fields.Date.to_string(approved_by_date) if approved_by_date else "-",
            "drawn_by_status": _name_or_status(latest_review.drawn_by_name, latest_review.tanda_tangan_shipyard) if latest_review else "Tidak",
            "designed_by_status": _name_or_status(latest_review.designed_by_name, latest_review.tanda_tangan_class) if latest_review else "Tidak",
            "checked_by_status": _name_or_status(latest_review.checked_by_name, latest_review.tanda_tangan_owner_delegate) if latest_review else "Tidak",
            "approved_by_status": _name_or_status(latest_review.approved_by_name, latest_review.tanda_tangan_owner_delegate) if latest_review else "Tidak",
            "approval_date": fields.Datetime.to_string(latest_review.tanggal_input) if latest_review and latest_review.tanggal_input else fields.Datetime.to_string(now_dt),
            "project_symbol_url": self._get_project_symbol_image_url(),
            "revision_rows": table_rows,
        }

    def _get_body_sheet_data(self):
        self.ensure_one()
        cover = self._get_cover_sheet_data()
        page5_labels = self._get_body_page5_labels()
        page6_defaults = self._get_body_page6_defaults()
        page6_static_rows = self._get_body_page6_static_rows()

        def _image_value(binary_value):
            if not binary_value:
                return ""
            if isinstance(binary_value, bytes):
                return binary_value.decode("utf-8")
            return str(binary_value)

        distributed_to_rows = [
            {
                "title": "SATGAS %s" % (self.nama_kapal or "FRIGATE 140 M"),
                "subtitle": "(Delegate of %s)" % (self.nama_kapal or "Frigate 140 M"),
            },
            {
                "title": "KEPALA DIVISI DESAIN",
                "subtitle": "(Head of Design Division)",
            },
            {
                "title": "KEPALA DEPARTEMEN QA/QC BANGUNAN KAPAL ATAS PERMUKAAN & KAPAL SELAM - DIVISI QA",
                "subtitle": "(Department of QA/QC Surface Ship & Submarine - Division of QA)",
            },
        ]
        role_rows = [
            {
                "label": "PEMBUAT",
                "role": "Author",
                "value": "DEPARTEMEN ISO, STANDARISASI & KALIBRASI - DIVISI QUALITY ASSURANCE",
                "subtitle": "(Department of ISO, Standardization & Calibration - Division of QA)",
            },
            {
                "label": "PELAKSANA",
                "role": "Inspector",
                "value": "DEPARTEMEN QA/QC BANGUNAN KAPAL ATAS PERMUKAAN & KAPAL SELAM - DIVISI QUALITY ASSURANCE",
                "subtitle": "(Department of QA/QC Surface Ship & Submarine - Division of QA)",
            },
            {
                "label": "PENDUKUNG PELAKSANA",
                "role": "Facilitator",
                "value": "DEPARTEMEN DESAIN STRUKTUR & PERLENGKAPAN LAMBUNG - DIVISI DESAIN",
                "subtitle": "(Department of Hull & Outfitting Design - Division of Design)",
            },
        ]
        toc_test_procedure_rows = [
            {"number": "1.", "title": "PENDAHULUAN", "subtitle": "Introduction", "page": "5"},
            {"number": "2.", "title": "UMUM", "subtitle": "General", "page": "5"},
            {"number": "3.", "title": "DOKUMEN PENDUKUNG", "subtitle": "Documents for the test", "page": "6"},
            {"number": "4.", "title": "REFERENSI PENDUKUNG", "subtitle": "References for the test", "page": "6"},
            {"number": "5.", "title": "KONDISI", "subtitle": "Condition", "page": "6"},
            {"number": "6.", "title": "WAKTU", "subtitle": "Time", "page": "6"},
            {"number": "7.", "title": "DEFINISI PENGUJIAN", "subtitle": "Definition of the Test", "page": "6"},
        ]
        if self.template_tptr == "davits_rhib":
            toc_test_record_rows = [
                {"number": "1.", "title": "UMUM", "subtitle": "General", "page": "8"},
                {"number": "2.", "title": "OBYEK PENGUJIAN", "subtitle": "Test Object", "page": "9"},
                {"number": "3.", "title": "PERALATAN YANG DIGUNAKAN", "subtitle": "Equipment to be Used", "page": "9"},
                {
                    "number": "4.",
                    "title": "PERSIAPAN SEBELUM PENGUJIAN",
                    "subtitle": "Preparation Before the Test",
                    "page": "10",
                },
                {"number": "5.", "title": "HASIL PENGUJIAN", "subtitle": "Test Result", "page": "10"},
                {"number": "6.", "title": "CATATAN", "subtitle": "Remark", "page": "12"},
            ]
        else:
            toc_test_record_rows = [
                {"number": "1.", "title": "UMUM", "subtitle": "General", "page": "10"},
                {"number": "2.", "title": "OBYEK PENGUJIAN", "subtitle": "Test Object", "page": "11"},
                {"number": "3.", "title": "PERALATAN YANG DIGUNAKAN", "subtitle": "Equipment to be Used", "page": "12"},
                {
                    "number": "4.",
                    "title": "PERSIAPAN SEBELUM PENGUJIAN",
                    "subtitle": "Preparation Before the Test",
                    "page": "13",
                },
                {"number": "5.", "title": "CATATAN", "subtitle": "Remark", "page": "16"},
            ]
        acceptance_rows = [
            {
                "acceptance": "Delegate Team",
                "name": self.body_delegate_name or self.delegasi_pemilik or "",
                "signature_image": _image_value(self.body_delegate_signature),
                "date": self.body_delegate_signature_date.strftime("%d/%m/%Y") if self.body_delegate_signature_date else "",
            },
            {
                "acceptance": "PT PAL Indonesia",
                "name": self.body_pt_pal_name or "",
                "signature_image": _image_value(self.body_pt_pal_signature),
                "date": self.body_pt_pal_signature_date.strftime("%d/%m/%Y") if self.body_pt_pal_signature_date else "",
            },
        ]
        supporting_reference_rows = [
            {"prefix": "-", "indent": 0, **row}
            for row in self._parse_body_page6_rows(self.body_supporting_reference or page6_defaults["supporting_reference"])
        ]
        condition_rows = [
            {"prefix": "-", "indent": 0, **row}
            for row in self._parse_body_page6_rows(self.body_condition or page6_defaults["condition"])
        ]
        time_rows = [
            {"prefix": "-", "indent": 0, **row}
            for row in self._parse_body_page6_rows(self.body_time or page6_defaults["time"])
        ]
        return {
            "project_name": cover["project_name"],
            "summary_footer_label": cover["summary_footer_label"],
            "body_page_number_label": cover["body_page_number_label"],
            "toc_page_number_label": cover["toc_page_number_label"],
            "intro_page_number_label": cover["intro_page_number_label"],
            "procedure_page_number_label": cover["procedure_page_number_label"],
            "distributed_to_rows": distributed_to_rows,
            "role_rows": role_rows,
            "toc_test_procedure_rows": toc_test_procedure_rows,
            "toc_test_record_rows": toc_test_record_rows,
            "intro_heading_main": page5_labels["headline_main"],
            "intro_heading_sub": page5_labels["headline_sub"],
            "intro_test_type_label": page5_labels["test_full_label"],
            "intro_test_object_label": page5_labels["object_label"],
            "intro_project_number_label": self._get_body_project_number_display(),
            "intro_test_related_project_no": self.body_test_related_project_no or "",
            "intro_document_number": cover["drw_document_no"],
            "intro_contract_specification": self.body_contract_specification or "",
            "intro_acceptance_rows": acceptance_rows,
            "procedure_document_rows": page6_static_rows["document_rows"],
            "procedure_supporting_reference_rows": supporting_reference_rows,
            "procedure_condition_rows": condition_rows,
            "procedure_time_rows": time_rows,
            "procedure_definition_rows": page6_static_rows["definition_rows"],
            "procedure_document_markup": self._build_body_page6_markup(page6_static_rows["document_rows"]),
            "procedure_supporting_reference_markup": self._build_body_page6_markup(supporting_reference_rows),
            "procedure_condition_markup": self._build_body_page6_markup(condition_rows),
            "procedure_time_markup": self._build_body_page6_markup(time_rows),
            "procedure_definition_markup": self._build_body_page6_markup(page6_static_rows["definition_rows"]),
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


class TptrPeralatan(models.Model):
    _name = "tptr.peralatan"
    _description = "Peralatan Yang Digunakan"
    _order = "sequence, id asc"

    kapal_id = fields.Many2one("pal.kapal.proyek", string="Proyek Kapal", ondelete="cascade", required=True)
    name_id = fields.Char(string="Nama Peralatan (ID)", required=True)
    name_en = fields.Char(string="Nama Peralatan (EN)", required=True)
    sequence = fields.Integer(string="Urutan", default=10)


class TptrCatatan(models.Model):
    _name = "tptr.catatan"
    _description = "Catatan dan Aksi Pengujian"
    _order = "sequence, id asc"

    kapal_id = fields.Many2one("pal.kapal.proyek", string="Proyek Kapal", ondelete="cascade", required=True)
    remark = fields.Char(string="Catatan (Remark)")
    action = fields.Char(string="Aksi (Action)")
    sequence = fields.Integer(string="Urutan", default=10)

