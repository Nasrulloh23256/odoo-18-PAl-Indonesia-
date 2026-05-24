# -*- coding: utf-8 -*-

import base64
import html
from typing import Any, Dict, Mapping, Optional
from urllib.parse import quote_plus

from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import content_disposition, request
from odoo.modules.module import get_module_resource


# Controller website ini menyediakan halaman CRUD Data Kapal & Proyek untuk user internal.
class DataKapalWebsiteController(http.Controller):
    def _get_tptr_template_profiles(self) -> Dict[str, Dict[str, str]]:
        return request.env["pal.kapal.proyek"]._get_tptr_template_profiles()

    def _get_tptr_template_profile(self, template_key: Optional[str] = None) -> Dict[str, str]:
        profiles = self._get_tptr_template_profiles()
        return dict(profiles.get((template_key or "").strip() or "rhib", profiles["rhib"]))

    def _decode_signature_data_url(self, data_url: str) -> bytes:
        raw_value = (data_url or "").strip()
        if not raw_value or "," not in raw_value:
            return b""
        try:
            return base64.b64decode(raw_value.split(",", 1)[1])
        except Exception:
            return b""

    def _extract_signature_input(self, upload_field_name: str, draw_field_name: str, default_filename: str):
        upload_file = request.httprequest.files.get(upload_field_name)
        if upload_file and upload_file.filename:
            upload_bytes = upload_file.read() or b""
            if upload_bytes:
                return upload_bytes, (upload_file.filename or "").strip() or default_filename

        drawn_bytes = self._decode_signature_data_url(request.params.get(draw_field_name) or "")
        if drawn_bytes:
            return drawn_bytes, default_filename
        return b"", ""

    # Helper ini menyiapkan payload write/create dari data form agar konsisten antar route.
    def _build_payload(self, post: Mapping[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "nama_kapal": (post.get("nama_kapal") or "").strip(),
            "nomor_proyek": (post.get("nomor_proyek") or "").strip(),
            "delegasi_pemilik": (post.get("delegasi_pemilik") or "").strip(),
            "jenis_tes": (post.get("jenis_tes") or "").strip(),
            "template_tptr": (post.get("template_tptr") or "").strip(),
        }

        kelas_kapal_raw = (post.get("kelas_kapal_id") or "").strip()
        if kelas_kapal_raw.isdigit():
            payload["kelas_kapal_id"] = int(kelas_kapal_raw)
        else:
            payload["kelas_kapal_id"] = None

        return payload

    # Validasi ini menjaga field wajib dan referensi master kelas kapal tetap valid.
    def _validate_payload(self, payload: Mapping[str, Any]) -> Optional[str]:
        if not payload.get("nama_kapal"):
            return "Nama Kapal wajib diisi."
        if not payload.get("nomor_proyek"):
            return "Nomor Proyek wajib diisi."

        kelas_kapal_id = payload.get("kelas_kapal_id")
        if not isinstance(kelas_kapal_id, int):
            return "Kelas Kapal wajib dipilih."

        if not request.env["pal.kapal.kelas"].browse(kelas_kapal_id).exists():
            return "Kelas Kapal yang dipilih tidak ditemukan."
        if not payload.get("delegasi_pemilik"):
            return "Delegasi Pemilik wajib diisi."
        if payload.get("jenis_tes") not in ("hat", "sat"):
            return "Jenis Tes wajib dipilih (HAT/SAT)."
        if payload.get("template_tptr") not in self._get_tptr_template_profiles():
            return "Template TPTR wajib dipilih."

        return None

    # Nilai context ini dipakai ulang untuk render halaman list + form create/edit.
    def _get_page_values(
        self,
        record: Any = None,
        form_data: Optional[Mapping[str, Any]] = None,
        error: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        kelas_kapals = request.env["pal.kapal.kelas"].search([], order="name asc")
        records = request.env["pal.kapal.proyek"].search([], order="id desc")

        base_data: Dict[str, Any] = {
            "nama_kapal": "",
            "nomor_proyek": "",
            "kelas_kapal_id": "",
            "delegasi_pemilik": "",
            "jenis_tes": "hat",
            "template_tptr": "rhib",
        }

        if record:
            base_data.update(
                {
                    "nama_kapal": record.nama_kapal or "",
                    "nomor_proyek": record.nomor_proyek or "",
                    "kelas_kapal_id": record.kelas_kapal_id.id or "",
                    "delegasi_pemilik": record.delegasi_pemilik or "",
                    "jenis_tes": record.jenis_tes or "hat",
                    "template_tptr": record.template_tptr or "rhib",
                }
            )

        if form_data:
            base_data.update(form_data)

        is_edit = bool(record)
        form_action = "/tptr/kapal-proyek/create"
        if is_edit:
            form_action = "/tptr/kapal-proyek/%s/update" % record.id

        return {
            "records": records,
            "kelas_kapals": kelas_kapals,
            "form_data": base_data,
            "is_edit": is_edit,
            "form_action": form_action,
            "edit_record": record,
            "error": error,
            "status": status,
        }

    # Helper ini membaca template HTML statis untuk halaman CRUD kapal/proyek (tanpa request.render QWeb).
    def _load_kapal_html_template(self) -> str:
        template_path = get_module_resource(
            "data_kapal",
            "static",
            "src",
            "html",
            "kapal_proyek_page.html",
        )
        if not template_path:
            raise UserError("Template HTML Data Kapal tidak ditemukan di modul data_kapal.")

        try:
            with open(template_path, "r", encoding="utf-8") as template_file:
                return template_file.read()
        except OSError as exc:
            raise UserError("Gagal membaca template HTML Data Kapal: %s" % exc)

    # Banner status dipakai untuk menampilkan feedback create/update/delete/validasi.
    def _build_kapal_status_block(self, status: Optional[str], error_message: Optional[str] = None) -> str:
        blocks = []
        if error_message:
            safe_message = html.escape(error_message, quote=True)
            blocks.append('<div class="alert alert-danger">%s</div>' % safe_message)

        status_map = {
            "created": ("success", "Data berhasil ditambahkan."),
            "updated": ("success", "Data berhasil diperbarui."),
            "deleted": ("success", "Data berhasil dihapus."),
            "not_found": ("warning", "Data tidak ditemukan."),
        }
        css_name, message = status_map.get(status, (None, None))
        if css_name and message:
            blocks.append('<div class="alert alert-%s">%s</div>' % (css_name, message))
        return "\n".join(blocks)

    # Render manual via string replacement agar halaman CRUD kapal memakai HTML/CSS custom tanpa QWeb.
    def _render_kapal_proyek_page(
        self,
        record: Any = None,
        form_data: Optional[Mapping[str, Any]] = None,
        error: Optional[str] = None,
        status: Optional[str] = None,
    ) -> str:
        values = self._get_page_values(record=record, form_data=form_data, error=error, status=status)
        template_html = self._load_kapal_html_template()
        csrf_token = request.csrf_token()
        status_block = self._build_kapal_status_block(status=values["status"], error_message=values["error"])

        selected_kelas_id = str(values["form_data"].get("kelas_kapal_id") or "")
        kelas_options = ['<option value="">Pilih kelas kapal...</option>']
        for kelas in values["kelas_kapals"]:
            selected_attr = ""
            if str(kelas.id) == selected_kelas_id:
                selected_attr = ' selected="selected"'
            kelas_options.append(
                '<option value="{id}"{selected}>{name}</option>'.format(
                    id=kelas.id,
                    selected=selected_attr,
                    name=html.escape(kelas.name or "", quote=True),
                )
            )

        rows = []
        for rec in values["records"]:
            jenis_tes = (rec.jenis_tes or "").upper()
            template_label = self._get_tptr_template_profile(rec.template_tptr).get("label", "RHIB")
            rows.append(
                (
                    "<tr>"
                    "<td>{nama_kapal}</td>"
                    "<td>{nomor_proyek}</td>"
                    "<td>{kelas_kapal}</td>"
                    "<td>{delegasi_pemilik}</td>"
                    "<td>{template_tptr}</td>"
                    "<td>{jenis_tes}</td>"
                    "<td>{tanggal_input}</td>"
                    '<td class="text-end">'
                    '<a href="/tptr/kapal-proyek?edit_id={id}" class="btn btn-sm btn-outline-primary">Edit</a>'
                    '<form action="/tptr/kapal-proyek/{id}/delete" method="post" class="inline-form" onsubmit="return confirm(\'Yakin ingin menghapus data ini?\');">'
                    '<input type="hidden" name="csrf_token" value="{csrf_token}" />'
                    '<button type="submit" class="btn btn-sm btn-outline-danger">Hapus</button>'
                    "</form>"
                    "</td>"
                    "</tr>"
                ).format(
                    id=rec.id,
                    nama_kapal=html.escape(rec.nama_kapal or "", quote=True),
                    nomor_proyek=html.escape(rec.nomor_proyek or "", quote=True),
                    kelas_kapal=html.escape(rec.kelas_kapal_id.name or "", quote=True),
                    delegasi_pemilik=html.escape(rec.delegasi_pemilik or "", quote=True),
                    template_tptr=html.escape(template_label, quote=True),
                    jenis_tes=html.escape(jenis_tes, quote=True),
                    tanggal_input=html.escape(str(rec.tanggal_input or ""), quote=True),
                    csrf_token=html.escape(csrf_token, quote=True),
                )
            )

        if not rows:
            rows.append('<tr><td colspan="8" class="empty-row">Belum ada data.</td></tr>')

        jenis_tes = values["form_data"].get("jenis_tes") or "hat"
        selected_template_tptr = values["form_data"].get("template_tptr") or "rhib"
        template_options = []
        for template_key, meta in self._get_tptr_template_profiles().items():
            selected_attr = ' selected="selected"' if selected_template_tptr == template_key else ""
            template_options.append(
                '<option value="{key}"{selected}>{label}</option>'.format(
                    key=html.escape(template_key, quote=True),
                    selected=selected_attr,
                    label=html.escape(meta["label"], quote=True),
                )
            )
        submit_label = "Update" if values["is_edit"] else "Simpan"
        page_subtitle = (
            "Mode edit data kapal/proyek."
            if values["is_edit"]
            else "Isi form berikut untuk menambah data kapal/proyek TPTR."
        )
        cancel_button = ""
        if values["is_edit"]:
            cancel_button = '<a href="/tptr/kapal-proyek" class="btn btn-secondary">Batal Edit</a>'

        replacements = {
            "__STATUS_BLOCK__": status_block,
            "__CSRF_TOKEN__": html.escape(csrf_token, quote=True),
            "__FORM_ACTION__": html.escape(values["form_action"], quote=True),
            "__FORM_TITLE__": "Edit Data Kapal" if values["is_edit"] else "Tambah Data Kapal",
            "__PAGE_SUBTITLE__": page_subtitle,
            "__NAMA_KAPAL__": html.escape(values["form_data"].get("nama_kapal") or "", quote=True),
            "__NOMOR_PROYEK__": html.escape(values["form_data"].get("nomor_proyek") or "", quote=True),
            "__KELAS_KAPAL_OPTIONS__": "\n".join(kelas_options),
            "__DELEGASI_PEMILIK__": html.escape(values["form_data"].get("delegasi_pemilik") or "", quote=True),
            "__TEMPLATE_TPTR_OPTIONS__": "\n".join(template_options),
            "__JENIS_HAT_SELECTED__": ' selected="selected"' if jenis_tes == "hat" else "",
            "__JENIS_SAT_SELECTED__": ' selected="selected"' if jenis_tes == "sat" else "",
            "__SUBMIT_LABEL__": submit_label,
            "__CANCEL_EDIT_BUTTON__": cancel_button,
            "__TABLE_ROWS__": "\n".join(rows),
        }

        rendered_html = template_html
        for placeholder, value in replacements.items():
            rendered_html = rendered_html.replace(placeholder, value)
        return rendered_html

    # Ambil record proyek dari query/form secara aman.
    def _get_project_from_id(self, project_id_raw: Any):
        if project_id_raw is None:
            return request.env["pal.kapal.proyek"]
        project_id_str = str(project_id_raw).strip()
        if not project_id_str.isdigit():
            return request.env["pal.kapal.proyek"]
        return request.env["pal.kapal.proyek"].browse(int(project_id_str)).exists()

    def _is_body_page_step_completed(self, project: Any) -> bool:
        if not project:
            return False
        return bool(
            (project.body_test_related_project_no or "").strip()
            and (project.body_contract_specification or "").strip()
        )

    def _is_body_page6_step_completed(self, project: Any) -> bool:
        if not project:
            return False
        return bool(
            (project.body_supporting_reference or "").strip()
            and (project.body_condition or "").strip()
            and (project.body_time or "").strip()
        )

    # Cegah user loncat step sebelum step sebelumnya selesai.
    def _guard_wizard_step(self, step: int, project: Any):
        if step == 0:
            return 0, ""
        if step > 1 and not project:
            return 1, "Selesaikan Step 1 (Data Kapal & Proyek) terlebih dahulu."
        if step > 2:
            lokasi_count = request.env["tptr.lokasi_kelas"].search_count([("kapal_id", "=", project.id)])
            if lokasi_count < 1:
                return 2, "Selesaikan Step 2 (Lokasi & Kelas Pengujian) terlebih dahulu."
        if step > 3:
            dokumen_count = request.env["tptr.dokumen_pendukung"].search_count([("tp_id", "=", project.id)])
            if dokumen_count < 1:
                return 3, "Selesaikan Step 3 (Dokumen Pendukung) terlebih dahulu."
        if step > 4 and not self._is_body_page_step_completed(project):
            return 4, "Selesaikan Step 4 (Body TPTR Halaman 5) terlebih dahulu."
        if step > 5 and not self._is_body_page6_step_completed(project):
            return 5, "Selesaikan Step 5 (Body TPTR Halaman 6) terlebih dahulu."
        if step > 6 and not project._is_test_record_general_completed():
            return 6, "Selesaikan Step 6 (Test Record Halaman 7) terlebih dahulu."
        if step > 7 and not project._is_test_record_spec_completed():
            return 7, "Selesaikan Step 7 (Test Record Spesifikasi) terlebih dahulu."
        if step > 8 and not project._is_test_procedure_checklist_completed():
            return 8, "Selesaikan Step 8 (Test Record Checklist) terlebih dahulu."
        return step, ""

    # Hitung step tertinggi yang saat ini sudah boleh diakses.
    def _get_max_available_step(self, project: Any) -> int:
        if not project:
            return 1
        max_step = 2
        lokasi_count = request.env["tptr.lokasi_kelas"].search_count([("kapal_id", "=", project.id)])
        if lokasi_count:
            max_step = 3
        dokumen_count = request.env["tptr.dokumen_pendukung"].search_count([("tp_id", "=", project.id)])
        if dokumen_count:
            max_step = 4
        if self._is_body_page_step_completed(project):
            max_step = 5
        if self._is_body_page6_step_completed(project):
            max_step = 6
        if project and project._is_test_record_general_completed():
            max_step = 7
        if project and project._is_test_record_spec_completed():
            max_step = 8
        if project and project._is_test_procedure_checklist_completed():
            max_step = 9
        return max_step

    # Baca template HTML wizard cover TPTR dari file statis (tanpa QWeb).
    def _load_cover_wizard_template(self) -> str:
        template_path = get_module_resource(
            "data_kapal",
            "static",
            "src",
            "html",
            "tptr_cover_wizard.html",
        )
        if not template_path:
            raise UserError("Template HTML wizard TPTR tidak ditemukan.")

        try:
            with open(template_path, "r", encoding="utf-8") as template_file:
                return template_file.read()
        except OSError as exc:
            raise UserError("Gagal membaca template HTML wizard TPTR: %s" % exc)

    # Bangun banner status/error untuk halaman wizard.
    def _build_cover_wizard_status_block(
        self,
        status: Optional[str] = None,
        error_message: Optional[str] = None,
        warning_message: Optional[str] = None,
    ) -> str:
        blocks = []
        status_messages = {
            "step1_saved": ("success", "Step 1 selesai. Lanjutkan ke Step 2."),
            "step2_saved": ("success", "Step 2 selesai. Lanjutkan ke Step 3."),
            "step3_saved": ("success", "Step 3 selesai. Lanjutkan ke Step 4."),
            "step4_saved": ("success", "Step 4 selesai. Lanjutkan ke Step 5."),
            "step5_saved": ("success", "Step 5 selesai. Lanjutkan ke Step 6."),
            "step6_saved": ("success", "Step 6 selesai. Lanjutkan ke Step 7."),
            "step7_saved": ("success", "Step 7 selesai. Lanjutkan ke Step 8."),
            "step8_saved": ("success", "Step 8 selesai. Lanjutkan ke Step 9."),
            "completed": ("success", "Semua step selesai. Data cover dan body TPTR siap dipakai."),
            "invalid_project": ("warning", "Project tidak ditemukan. Silakan mulai dari Step 1."),
        }
        css_class, message = status_messages.get(status, (None, None))
        if css_class and message:
            blocks.append('<div class="wizard-alert wizard-%s">%s</div>' % (css_class, message))
        if warning_message:
            blocks.append(
                '<div class="wizard-alert wizard-warning">%s</div>'
                % html.escape(warning_message, quote=True)
            )
        if error_message:
            blocks.append(
                '<div class="wizard-alert wizard-danger">%s</div>'
                % html.escape(error_message, quote=True)
            )
        return "\n".join(blocks)

    # Komponen progress stepper (warna navy) untuk menampilkan status step saat ini.
    def _build_cover_wizard_stepper(self, current_step: int, project: Any) -> str:
        steps = [
            (1, "Data Kapal & Proyek", "Informasi dasar kapal/proyek."),
            (2, "Lokasi & Kelas Pengujian", "Lokasi uji dan status sign class."),
            (3, "Dokumen Pendukung", "Referensi desain dan dokumen maker."),
            (4, "Body TPTR Halaman 5", "Konten pendahuluan, kontrak, dan acceptance."),
            (5, "Body TPTR Halaman 6", "Dokumen pendukung, referensi, kondisi, dan waktu."),
            (6, "Test Record Halaman 7", "Tanggal, tempat, dan pelaksana tim penguji."),
            (7, "Test Record Spesifikasi", "Spesifikasi obyek dan persiapan pengujian."),
            (8, "Test Record Checklist", "Checklist pengujian halaman 10-12."),
            (9, "Review & Persetujuan", "Status review dan tanda tangan."),
        ]
        max_available_step = self._get_max_available_step(project)

        items = []
        for step_no, title, subtitle in steps:
            if step_no < current_step:
                css_class = "done"
                marker = "&#10003;"
            elif step_no == current_step:
                css_class = "active"
                marker = "%02d" % step_no
            else:
                css_class = "todo"
                marker = "%02d" % step_no

            if step_no <= max_available_step and project:
                href = "/tptr/cover-wizard?step=%s&project_id=%s" % (step_no, project.id)
                title_html = '<a href="%s">%s</a>' % (href, html.escape(title, quote=True))
            elif step_no == 1:
                title_html = '<a href="/tptr/cover-wizard?step=1">%s</a>' % html.escape(title, quote=True)
            else:
                title_html = html.escape(title, quote=True)

            items.append(
                (
                    '<li class="wizard-step {css}">'
                    '<span class="wizard-node">{marker}</span>'
                    '<h3>{title}</h3>'
                    '<p>{subtitle}</p>'
                    "</li>"
                ).format(
                    css=css_class,
                    marker=marker,
                    title=title_html,
                    subtitle=html.escape(subtitle, quote=True),
                )
            )
        return '<ol class="wizard-stepper">%s</ol>' % "".join(items)

    def _format_wizard_datetime(self, value: Any) -> str:
        if not value:
            return "-"
        if hasattr(value, "strftime"):
            return value.strftime("%d/%m/%Y %H:%M")
        return str(value)

    def _get_wizard_status_class(self, status_label: str) -> str:
        normalized = (status_label or "").strip().lower()
        if normalized.startswith("disetujui"):
            return "wizard-status-success"
        if normalized.startswith("menunggu"):
            return "wizard-status-waiting"
        return "wizard-status-progress"

    def _get_cover_wizard_step_meta(self, step: int) -> Dict[str, str]:
        step_map: Dict[int, Dict[str, str]] = {
            1: {
                "title": "Data Kapal & Proyek",
                "summary": "Isi identitas dasar kapal, nomor proyek, kelas kapal, dan jenis tes untuk membuka step berikutnya.",
                "next": "Lokasi & Kelas Pengujian",
            },
            2: {
                "title": "Lokasi & Kelas Pengujian",
                "summary": "Lengkapi lokasi pengujian, status sign class, dan catatan teknis yang dibutuhkan.",
                "next": "Dokumen Pendukung",
            },
            3: {
                "title": "Dokumen Pendukung",
                "summary": "Masukkan referensi desain dan dokumen maker agar cover TPTR siap direview.",
                "next": "Body TPTR Halaman 5",
            },
            4: {
                "title": "Body TPTR Halaman 5",
                "summary": "Lengkapi pengujian untuk nomor proyek, spesifikasi kontrak, dan tanda tangan acceptance untuk halaman 5 body TPTR.",
                "next": "Body TPTR Halaman 6",
            },
            5: {
                "title": "Body TPTR Halaman 6",
                "summary": "Lengkapi referensi pendukung, kondisi, dan waktu pengujian untuk halaman 6 body TPTR.",
                "next": "Test Record Halaman 7",
            },
            6: {
                "title": "Test Record Halaman 7",
                "summary": "Lengkapi tanggal, tempat, ketua tim, anggota tim penguji, dan penanggung jawab uji lainnya.",
                "next": "Test Record Spesifikasi",
            },
            7: {
                "title": "Test Record Spesifikasi",
                "summary": "Lengkapi spesifikasi obyek pengujian (Davit / RHIB) dan persiapan sebelum pengujian.",
                "next": "Test Record Checklist",
            },
            8: {
                "title": "Test Record Checklist",
                "summary": "Lengkapi daftar checklist pengujian OK/NOT OK untuk Rigid Hull Inflatable Boat (RHIB) halaman 10 sampai 12.",
                "next": "Review & Persetujuan",
            },
            9: {
                "title": "Review & Persetujuan",
                "summary": "Tentukan status review dan kelengkapan persetujuan sebelum file diteruskan ke Jasper.",
                "next": "Jasper Cover & Finalisasi",
            },
        }
        return step_map.get(
            step,
            {
                "title": "Hub Project TPTR",
                "summary": "Pusat kerja untuk melihat daftar project cover, memilih template dokumen, memilih project aktif, dan membuka wizard pengisian.",
                "next": "Pilih Template & Step 1",
            },
        )

    def _build_cover_wizard_page_intro(self, step: int, project: Any) -> str:
        meta = self._get_cover_wizard_step_meta(step)
        total_projects = request.env["pal.kapal.proyek"].search_count([])

        if step == 0:
            return (
                '<section class="wizard-intro">'
                '<div class="wizard-intro-copy">'
                '<p class="wizard-section-badge">COVER WORKSPACE</p>'
                '<h2>Hub Project untuk Cover TPTR</h2>'
                '<p>{summary}</p>'
                "</div>"
                '<div class="wizard-intro-grid">'
                '<article class="wizard-intro-card">'
                '<p class="wizard-intro-label">Mode Saat Ini</p>'
                '<h3 class="wizard-intro-value">Hub Project</h3>'
                '<p class="wizard-intro-note">{project_total} project tersedia</p>'
                "</article>"
                '<article class="wizard-intro-card">'
                '<p class="wizard-intro-label">Yang Bisa Dilakukan</p>'
                '<h3 class="wizard-intro-value">Pilih, lanjutkan, atau buat project baru</h3>'
                '<p class="wizard-intro-note">Hubungkan daftar project dengan wizard tanpa masuk backend lebih dulu.</p>'
                "</article>"
                '<article class="wizard-intro-card">'
                '<p class="wizard-intro-label">Alur Kerja</p>'
                '<h3 class="wizard-intro-value">Hub Project -> Pilih Template -> Step 1-8 -> Jasper</h3>'
                '<p class="wizard-intro-note">Data cover dan body TPTR dirapikan dulu sebelum file dicetak.</p>'
                "</article>"
                "</div>"
                "</section>"
            ).format(summary=html.escape(meta["summary"], quote=True), project_total=total_projects)

        project_name = project.nama_kapal if project and project.nama_kapal else "Belum ada project aktif"
        project_hint = (
            project.nomor_proyek if project and project.nomor_proyek else "Pilih project dari dropdown atau kembali ke hub project"
        )
        status_hint = (
            project.status_tptr if project and project.status_tptr else "Project belum memiliki status TPTR"
        )
        if not project:
            status_hint = "Aktifkan project untuk melanjutkan step"
        return (
            '<section class="wizard-intro">'
            '<div class="wizard-intro-copy">'
            '<p class="wizard-section-badge">COVER WIZARD</p>'
            '<h2>Step {step}: {title}</h2>'
            '<p>{summary}</p>'
            "</div>"
            '<div class="wizard-intro-grid">'
            '<article class="wizard-intro-card">'
            '<p class="wizard-intro-label">Step Aktif</p>'
            '<h3 class="wizard-intro-value">Step {step} dari 9</h3>'
            '<p class="wizard-intro-note">{title}</p>'
            "</article>"
            '<article class="wizard-intro-card">'
            '<p class="wizard-intro-label">Project Aktif</p>'
            '<h3 class="wizard-intro-value">{project_name}</h3>'
            '<p class="wizard-intro-note">{project_hint}</p>'
            "</article>"
            '<article class="wizard-intro-card">'
            '<p class="wizard-intro-label">Target Berikutnya</p>'
            '<h3 class="wizard-intro-value">{next_step}</h3>'
            '<p class="wizard-intro-note">{status_hint}</p>'
            "</article>"
            "</div>"
            "</section>"
        ).format(
            step=step,
            title=html.escape(meta["title"], quote=True),
            summary=html.escape(meta["summary"], quote=True),
            project_name=html.escape(project_name, quote=True),
            project_hint=html.escape(project_hint, quote=True),
            next_step=html.escape(meta["next"], quote=True),
            status_hint=html.escape(status_hint, quote=True),
        )

    # Ringkasan project aktif agar user selalu tahu konteks project yang sedang diisi.
    def _build_cover_wizard_project_summary(self, project: Any, current_step: int) -> str:
        records = request.env["pal.kapal.proyek"].search([], order="id desc")
        active_id = project.id if project else None
        safe_step = max(int(current_step or 1), 1)
        record_total = len(records)

        rows = []
        for rec in records:
            row_css = ' class="is-active"' if active_id and rec.id == active_id else ""
            status_label = rec.status_tptr or "-"
            template_label = self._get_tptr_template_profile(rec.template_tptr).get("label", "RHIB")
            nomor_dokumen = html.escape(rec.nomor_dokumen_utama or "-", quote=True)
            nama_dokumen = html.escape(rec.nama_dokumen_utama or "-", quote=True)
            nama_project = html.escape(rec.nama_kapal or "-", quote=True)
            nomor_proyek = html.escape(rec.nomor_proyek or "-", quote=True)
            owner = html.escape(rec.delegasi_pemilik or "-", quote=True)
            tanggal_dibuat = html.escape(self._format_wizard_datetime(rec.tanggal_dibuat_document), quote=True)
            terakhir_diedit = html.escape(self._format_wizard_datetime(rec.terakhir_diedit_document), quote=True)
            rows.append(
                (
                    "<tr{row_css}>"
                    '<td class="wizard-col-doc-no">'
                    '<div class="wizard-cell-stack">'
                    '<span class="wizard-cell-chip" title="{nomor_dokumen}">{nomor_dokumen}</span>'
                    '<span class="wizard-cell-meta" title="{nomor_proyek}">{nomor_proyek}</span>'
                    "</div>"
                    "</td>"
                    '<td class="wizard-col-doc-name">'
                    '<div class="wizard-cell-clamp" title="{nama_dokumen}">{nama_dokumen}</div>'
                    "</td>"
                    '<td class="wizard-col-project">'
                    '<div class="wizard-cell-stack">'
                    '<strong class="wizard-cell-primary" title="{nama_project}">{nama_project}</strong>'
                    '<span class="wizard-cell-meta" title="{owner}">{owner} | {template_label}</span>'
                    "</div>"
                    "</td>"
                    '<td class="wizard-col-created"><div class="wizard-cell-datetime">{tanggal_dibuat}</div></td>'
                    '<td class="wizard-col-updated"><div class="wizard-cell-datetime">{terakhir_diedit}</div></td>'
                    '<td class="wizard-col-status"><span class="wizard-status {status_css}">{status}</span></td>'
                    '<td class="wizard-row-links">'
                    '<div class="wizard-row-action-group">'
                    '<a class="wizard-link" href="/tptr/cover-wizard?step={step}&project_id={id}">Lanjutkan</a>'
                    '<a class="wizard-link wizard-link-soft" href="/web#id={id}&model=pal.kapal.proyek&view_type=form">Backend</a>'
                    "</div>"
                    "</td>"
                    "</tr>"
                ).format(
                    row_css=row_css,
                    nomor_dokumen=nomor_dokumen,
                    nama_dokumen=nama_dokumen,
                    nama_project=nama_project,
                    nomor_proyek=nomor_proyek,
                    owner=owner,
                    template_label=html.escape(template_label, quote=True),
                    tanggal_dibuat=tanggal_dibuat,
                    terakhir_diedit=terakhir_diedit,
                    status_css=self._get_wizard_status_class(status_label),
                    status=html.escape(status_label, quote=True),
                    step=safe_step,
                    id=rec.id,
                )
            )

        if not rows:
            rows.append(
                '<tr><td colspan="7" class="wizard-empty-row">Belum ada data TPTR. Mulai dari Step 1 untuk membuat project baru.</td></tr>'
            )

        active_panel = (
            '<div class="wizard-active-panel empty">'
            '<div class="wizard-active-top">'
            '<div class="wizard-active-copy">'
            '<p class="wizard-section-badge">PROJECT AKTIF</p>'
            '<h3>Belum ada project aktif</h3>'
            '<p>Pilih project dari tabel TPTR Pusat atau mulai dari Step 1 untuk membuat data baru.</p>'
            "</div>"
            '<div class="wizard-active-side wizard-active-side-inline" style="display:flex;align-items:center;justify-content:flex-end;gap:16px;flex-wrap:wrap;">'
            '<span class="wizard-active-pill" style="white-space:nowrap;">Siap Mulai</span>'
            '<a class="wizard-btn wizard-btn-primary wizard-btn-cta" href="/tptr/cover-wizard?step=1">Pilih Template &amp; Buat Project Baru</a>'
            "</div>"
            "</div>"
            "</div>"
        )
        if project:
            lokasi_count = request.env["tptr.lokasi_kelas"].search_count([("kapal_id", "=", project.id)])
            dokumen_count = request.env["tptr.dokumen_pendukung"].search_count([("tp_id", "=", project.id)])
            review_count = request.env["tptr.review_persetujuan"].search_count([("tp_id", "=", project.id)])
            active_panel = (
                '<div class="wizard-active-panel">'
                '<div class="wizard-active-top">'
                '<div class="wizard-active-copy">'
                '<p class="wizard-section-badge">PROJECT AKTIF</p>'
                '<h3>{project}</h3>'
                '<p>{project_no} | {kelas} | {owner} | {template_label}</p>'
                "</div>"
                '<div class="wizard-active-side">'
                '<span class="wizard-active-pill">Step {step}</span>'
                "</div>"
                "</div>"
                '<div class="wizard-project-grid">'
                '<article><span>Nomor Dokumen</span><strong>{nomor_dokumen}</strong></article>'
                '<article><span>Nama Dokumen</span><strong>{nama_dokumen}</strong></article>'
                '<article><span>Template</span><strong>{template_label}</strong></article>'
                '<article><span>Progress Data</span><strong>L{lokasi} / D{dokumen} / R{review}</strong></article>'
                '<article><span>Status TPTR</span><strong>{status}</strong></article>'
                "</div>"
                '<div class="wizard-project-actions">'
                '<a class="wizard-btn wizard-btn-soft" href="/tptr/jasper-cover?project_id={id}">Buka Jasper Cover</a>'
                '<a class="wizard-btn wizard-btn-soft" href="/web#id={id}&model=pal.kapal.proyek&view_type=form">Buka Form Backend</a>'
                "</div>"
                "</div>"
            ).format(
                project=html.escape(project.nama_kapal or "-", quote=True),
                project_no=html.escape(project.nomor_proyek or "-", quote=True),
                kelas=html.escape(project.kelas_kapal or "-", quote=True),
                owner=html.escape(project.delegasi_pemilik or "-", quote=True),
                template_label=html.escape(
                    self._get_tptr_template_profile(project.template_tptr).get("label", "RHIB"),
                    quote=True,
                ),
                nomor_dokumen=html.escape(project.nomor_dokumen_utama or "-", quote=True),
                nama_dokumen=html.escape(project.nama_dokumen_utama or "-", quote=True),
                lokasi=lokasi_count,
                dokumen=dokumen_count,
                review=review_count,
                status=html.escape(project.status_tptr or "-", quote=True),
                id=project.id,
                step=safe_step,
            )

        return (
            '<section class="wizard-project-summary">'
            '<div class="wizard-panel-head">'
            '<div>'
            '<p class="wizard-section-badge">TPTR PUSAT</p>'
            '<h2>Ringkasan TPTR seperti halaman backend</h2>'
            '<p class="wizard-summary-subtitle">Kolom utama backend TPTR ditampilkan di wizard agar monitoring project tetap terpusat.</p>'
            "</div>"
            '<img class="wizard-panel-logo" src="/data_kapal/static/src/img/pal_logo.svg" alt="PAL Indonesia" />'
            "</div>"
            "{active_panel}"
            "</section>"
        ).format(active_panel=active_panel)

    def _build_cover_wizard_hub_view(self) -> str:
        records = request.env["pal.kapal.proyek"].search([], order="id desc")
        total_records = len(records)
        approved_total = 0
        waiting_total = 0
        rows = []
        for rec in records:
            raw_status = rec.status_tptr or "-"
            status_label = html.escape(raw_status, quote=True)
            nomor_dokumen = html.escape(rec.nomor_dokumen_utama or "-", quote=True)
            nama_dokumen = html.escape(rec.nama_dokumen_utama or "-", quote=True)
            nama_project = html.escape(rec.nama_kapal or "-", quote=True)
            nomor_proyek = html.escape(rec.nomor_proyek or "-", quote=True)
            owner = html.escape(rec.delegasi_pemilik or "-", quote=True)
            class_name = html.escape(rec.kelas_kapal or "-", quote=True)
            template_label = html.escape(
                self._get_tptr_template_profile(rec.template_tptr).get("label", "RHIB"),
                quote=True,
            )
            tanggal_dibuat = html.escape(self._format_wizard_datetime(rec.tanggal_dibuat_document), quote=True)
            terakhir_diedit = html.escape(self._format_wizard_datetime(rec.terakhir_diedit_document), quote=True)
            status_css = self._get_wizard_status_class(raw_status)
            normalized_status = (raw_status or "").strip().lower()
            if normalized_status.startswith("disetujui"):
                approved_total += 1
            elif normalized_status.startswith("menunggu") or "butuh" in normalized_status:
                waiting_total += 1

            search_blob = html.escape(
                " ".join(
                    filter(
                        None,
                        [
                            rec.nomor_dokumen_utama or "",
                            rec.nama_dokumen_utama or "",
                            rec.nama_kapal or "",
                            rec.nomor_proyek or "",
                            rec.delegasi_pemilik or "",
                            rec.kelas_kapal or "",
                            self._get_tptr_template_profile(rec.template_tptr).get("label", ""),
                            raw_status,
                        ],
                    )
                ).lower(),
                quote=True,
            )
            rows.append(
                (
                    '<tr class="wizard-hub-row" data-hub-row="1" data-search="{search_blob}" onclick="window.location=\'/tptr/cover-wizard?step=1&amp;project_id={id}\'">'
                    '<td class="wizard-col-doc-no">'
                    '<div class="wizard-cell-stack">'
                    '<span class="wizard-cell-chip" title="{nomor_dokumen}">{nomor_dokumen}</span>'
                    '<span class="wizard-cell-meta" title="{nomor_proyek}">{nomor_proyek}</span>'
                    "</div>"
                    "</td>"
                    '<td class="wizard-col-doc-name"><div class="wizard-cell-clamp" title="{nama_dokumen}">{nama_dokumen}</div></td>'
                    '<td class="wizard-col-project">'
                    '<div class="wizard-cell-stack">'
                    '<strong class="wizard-cell-primary" title="{nama_project}">{nama_project}</strong>'
                    '<span class="wizard-cell-meta" title="{owner}">{owner} | {class_name} | {template_label}</span>'
                    "</div>"
                    "</td>"
                    '<td class="wizard-col-created"><div class="wizard-cell-datetime">{tanggal_dibuat}</div></td>'
                    '<td class="wizard-col-updated"><div class="wizard-cell-datetime">{terakhir_diedit}</div></td>'
                    '<td class="wizard-col-status"><span class="wizard-status {status_css}">{status}</span></td>'
                    '<td class="wizard-row-links">'
                    '<div class="wizard-row-action-group">'
                    '<a class="wizard-link" href="/tptr/cover-wizard?step=1&amp;project_id={id}" onclick="event.stopPropagation();">Lanjutkan</a>'
                    '<a class="wizard-link wizard-link-soft" href="/web#id={id}&model=pal.kapal.proyek&view_type=form" onclick="event.stopPropagation();">Backend</a>'
                    "</div>"
                    "</td>"
                    "</tr>"
                ).format(
                    id=rec.id,
                    search_blob=search_blob,
                    nomor_dokumen=nomor_dokumen,
                    nomor_proyek=nomor_proyek,
                    nama_dokumen=nama_dokumen,
                    nama_project=nama_project,
                    owner=owner,
                    class_name=class_name,
                    template_label=template_label,
                    tanggal_dibuat=tanggal_dibuat,
                    terakhir_diedit=terakhir_diedit,
                    status=status_label,
                    status_css=status_css,
                )
            )

        draft_total = max(total_records - approved_total - waiting_total, 0)
        search_empty_row = ""
        if not rows:
            rows.append(
                '<tr><td colspan="7" class="wizard-empty-row">Belum ada project cover TPTR. Mulai dari tombol "Project Baru" untuk membuat data baru.</td></tr>'
            )
        else:
            search_empty_row = (
                '<tr id="wizard_hub_empty_search" style="display:none;">'
                '<td colspan="7" class="wizard-empty-row">Project tidak ditemukan. Coba kata kunci lain.</td>'
                "</tr>"
            )

        search_script = ""
        if total_records:
            search_script = (
                "<script>"
                "(function(){"
                "var input=document.getElementById('wizard_hub_search');"
                "var rows=[].slice.call(document.querySelectorAll('[data-hub-row]'));"
                "var empty=document.getElementById('wizard_hub_empty_search');"
                "if(!input||!rows.length){return;}"
                "var sync=function(){"
                "var query=(input.value||'').toLowerCase().trim();"
                "var visible=0;"
                "rows.forEach(function(row){"
                "var haystack=(row.getAttribute('data-search')||'');"
                "var matched=!query||haystack.indexOf(query)!==-1;"
                "row.style.display=matched?'':'none';"
                "if(matched){visible+=1;}"
                "});"
                "if(empty){empty.style.display=visible===0?'table-row':'none';}"
                "};"
                "input.addEventListener('input',sync);"
                "sync();"
                "})();"
                "</script>"
            )

        return (
            '<section class="wizard-project-summary wizard-project-hub">'
            '<div class="wizard-panel-head">'
            '<div>'
            '<p class="wizard-section-badge">PROJECT HUB</p>'
            '<h2>Daftar Project Cover TPTR</h2>'
            '<p class="wizard-summary-subtitle">Pilih project yang ingin dilanjutkan, lihat statusnya, lalu buka wizard atau backend dari satu tempat.</p>'
            "</div>"
            '<div class="wizard-project-actions">'
            '<a class="wizard-btn wizard-btn-primary" href="/tptr/cover-wizard?step=1">Pilih Template</a>'
            '<a class="wizard-btn wizard-btn-soft" href="/tptr/review-persetujuan">Halaman Review</a>'
            "</div>"
            "</div>"
            '<div class="wizard-project-grid wizard-hub-stats">'
            '<article><span>Total Project</span><strong>{total_records}</strong></article>'
            '<article><span>Butuh Tindak Lanjut</span><strong>{waiting_total}</strong></article>'
            '<article><span>Sudah Disetujui</span><strong>{approved_total}</strong></article>'
            '<article><span>Draft / Progress</span><strong>{draft_total}</strong></article>'
            "</div>"
            '<div class="wizard-hub-toolbar wizard-hub-toolbar-search">'
            '<label class="wizard-hub-search">'
            '<span class="wizard-hub-search-icon">&#128269;</span>'
            '<input id="wizard_hub_search" type="search" placeholder="Cari nomor dokumen, nama dokumen, project, owner, atau class..." />'
            "</label>"
            '<p class="wizard-hub-toolbar-note">Klik baris atau tombol "Lanjutkan" untuk membuka wizard cover dari project yang dipilih.</p>'
            "</div>"
            '<div class="wizard-hub-table-wrap">'
            '<table class="wizard-hub-table wizard-hub-table-main">'
            "<colgroup>"
            '<col class="wizard-col-doc-no" />'
            '<col class="wizard-col-doc-name" />'
            '<col class="wizard-col-project" />'
            '<col class="wizard-col-created" />'
            '<col class="wizard-col-updated" />'
            '<col class="wizard-col-status" />'
            '<col class="wizard-col-actions" />'
            "</colgroup>"
            "<thead>"
            "<tr>"
            '<th class="wizard-col-doc-no">Nomor Dokumen</th>'
            '<th class="wizard-col-doc-name">Nama Dokumen</th>'
            '<th class="wizard-col-project">Project</th>'
            '<th class="wizard-col-created">Tanggal Dibuat</th>'
            '<th class="wizard-col-updated">Terakhir Diedit</th>'
            '<th class="wizard-col-status">Status TPTR</th>'
            '<th class="text-end wizard-col-actions">Aksi</th>'
            "</tr>"
            "</thead>"
            "<tbody>{rows}{search_empty_row}</tbody>"
            "</table>"
            "</div>"
            "{search_script}"
            "</section>"
        ).format(
            total_records=total_records,
            waiting_total=waiting_total,
            approved_total=approved_total,
            draft_total=draft_total,
            rows="".join(rows),
            search_empty_row=search_empty_row,
            search_script=search_script,
        )

    # Dropdown proyek existing untuk melanjutkan step yang belum selesai.
    def _build_cover_wizard_resume_options(self, selected_project: Any) -> str:
        projects = request.env["pal.kapal.proyek"].search([], order="id desc")
        options = ['<option value="">Pilih project...</option>']
        selected_id = selected_project.id if selected_project else None

        for project in projects:
            selected_attr = ""
            if selected_id and project.id == selected_id:
                selected_attr = ' selected="selected"'
            label = "[%s] %s - %s" % (
                project.nomor_dokumen_utama or "-",
                project.nomor_proyek or "-",
                project.nama_kapal or "Tanpa Nama",
            )
            template_label = self._get_tptr_template_profile(project.template_tptr).get("label", "RHIB")
            options.append(
                '<option value="{id}"{selected}>{label}</option>'.format(
                    id=project.id,
                    selected=selected_attr,
                    label=html.escape("%s | %s" % (label, template_label), quote=True),
                )
            )
        return "\n".join(options)

    # Render form sesuai step aktif.
    def _build_cover_wizard_step_form(
        self,
        step: int,
        project: Any,
        csrf_token: str,
        form_data: Optional[Mapping[str, Any]] = None,
        selected_template_tptr: Optional[str] = None,
    ) -> str:
        form_data = dict(form_data or {})

        if step == 1:
            kelas_records = request.env["pal.kapal.kelas"].search([], order="name asc")
            selected_template = (
                (form_data.get("template_tptr") or "").strip()
                or (project.template_tptr if project else "")
                or (selected_template_tptr or "").strip()
            )
            if selected_template not in self._get_tptr_template_profiles():
                selected_template = ""

            if not project and not selected_template:
                template_rows = []
                footer_items = []
                for index, (template_key, meta) in enumerate(self._get_tptr_template_profiles().items(), start=1):
                    row_background = "#dbe7f6" if index % 2 == 1 else "#ffffff"
                    template_rows.append(
                        (
                            '<tr class="wizard-template-row" data-template-row="{key}" data-row-bg="{row_background}" style="background:{row_background};">'
                            '<td class="wizard-template-pick" style="width:78px; text-align:center; border:1px solid #b7c9df; padding:13px 12px;">'
                            '<label class="wizard-template-check">'
                            '<input type="checkbox" value="{key}" data-template-input="{key}" />'
                            '<span></span>'
                            '</label>'
                            "</td>"
                            '<td class="wizard-template-no" style="width:64px; text-align:center; border:1px solid #b7c9df; padding:13px 12px; font-weight:700; color:#0f3d75;">{index}</td>'
                            '<td class="wizard-template-name" style="border:1px solid #b7c9df; padding:13px 12px; font-size:17px; font-weight:700; color:#113b70;">{label}</td>'
                            '<td class="wizard-template-desc" style="border:1px solid #b7c9df; padding:13px 12px; font-size:17px; color:#14355f;">{doc_no}</td>'
                            "</tr>"
                        ).format(
                            key=html.escape(template_key, quote=True),
                            index=index,
                            row_background=row_background,
                            label=html.escape(meta["label"], quote=True),
                            doc_no=html.escape(meta["drawing_document_name"], quote=True),
                        )
                    )
                    footer_items.append(
                        '<li><strong>Template {index}:</strong> <span>{footer_label}</span></li>'.format(
                            index=index,
                            footer_label=html.escape(meta["footer_label"], quote=True),
                        )
                    )
                script_block = (
                    "<script>"
                    "(function(){"
                    "var inputs=[].slice.call(document.querySelectorAll('[data-template-input]'));"
                    "var hidden=document.getElementById('wizard_template_tptr_value');"
                    "var submit=document.getElementById('wizard_template_submit');"
                    "if(!inputs.length||!hidden||!submit){return;}"
                    "var sync=function(activeValue){"
                    "var hasValue=false;"
                    "inputs.forEach(function(input){"
                    "var checked=input.value===activeValue;"
                    "input.checked=checked;"
                    "var row=input.closest('tr');"
                    "if(row){"
                    "row.classList.toggle('is-selected', checked);"
                    "row.style.background=checked?'#c6d8f2':(row.getAttribute('data-row-bg')||'#ffffff');"
                    "}"
                    "if(checked){hasValue=true;}"
                    "});"
                    "hidden.value=hasValue?activeValue:'';"
                    "submit.disabled=!hasValue;"
                    "};"
                    "inputs.forEach(function(input){"
                    "input.addEventListener('change', function(){"
                    "sync(input.checked ? input.value : '');"
                    "});"
                    "var row=input.closest('tr');"
                    "if(row){"
                    "row.addEventListener('click', function(event){"
                    "if(event.target && event.target.tagName==='INPUT'){return;}"
                    "sync(input.value);"
                    "});"
                    "}"
                    "});"
                    "sync('');"
                    "})();"
                    "</script>"
                )
                return (
                    '<div class="wizard-template-picker-head">'
                    '<span class="wizard-section-badge">Template Picker</span>'
                    '<h2>Pilih Template TPTR</h2>'
                    '<p class="wizard-help">Tentukan template dokumen terlebih dahulu, lalu lanjutkan ke Step 1 untuk mengisi data project.</p>'
                    '<p class="wizard-template-picker-note">Centang kolom <span>&ldquo;Pilih&rdquo;</span> untuk memilih template, lalu klik tombol <strong>Lanjut</strong> di bawah.</p>'
                    "</div>"
                    '<form method="get" action="/tptr/cover-wizard" class="wizard-template-form">'
                    '<input type="hidden" name="step" value="1" />'
                    '<input type="hidden" name="template_tptr" id="wizard_template_tptr_value" value="" />'
                    '<div class="wizard-template-table-wrap">'
                    '<table class="wizard-template-table" style="width:100%; border-collapse:collapse; border:1px solid #b7c9df;">'
                    '<thead>'
                    '<tr>'
                    '<th class="wizard-template-pick" style="background:#23466e; color:#ffffff; border:1px solid #b7c9df; padding:13px 12px;">Pilih</th>'
                    '<th class="wizard-template-no" style="background:#23466e; color:#ffffff; border:1px solid #b7c9df; padding:13px 12px;">No.</th>'
                    '<th class="wizard-template-name" style="background:#23466e; color:#ffffff; border:1px solid #b7c9df; padding:13px 12px;">Template</th>'
                    '<th class="wizard-template-desc" style="background:#23466e; color:#ffffff; border:1px solid #b7c9df; padding:13px 12px;">Deskripsi Lengkap</th>'
                    "</tr>"
                    "</thead>"
                    "<tbody>{rows}</tbody>"
                    "</table>"
                    "</div>"
                    '<div class="wizard-template-actions">'
                    '<button id="wizard_template_submit" type="submit" class="wizard-template-submit" disabled>Lanjut ke Step 1 <span>&#10148;</span></button>'
                    "</div>"
                    "</form>"
                    '<section class="wizard-template-footer-preview">'
                    '<h3>Preview Footer:</h3>'
                    '<ul>{footer_items}</ul>'
                    "</section>"
                    "{script_block}"
                ).format(
                    rows="".join(template_rows),
                    footer_items="".join(footer_items),
                    script_block=script_block,
                )

            if project and not form_data:
                form_data = {
                    "project_id": project.id,
                    "nama_kapal": project.nama_kapal or "",
                    "nomor_proyek": project.nomor_proyek or "",
                    "kelas_kapal_id": project.kelas_kapal_id.id or "",
                    "delegasi_pemilik": project.delegasi_pemilik or "",
                    "jenis_tes": project.jenis_tes or "hat",
                    "template_tptr": project.template_tptr or "rhib",
                }
                selected_template = form_data["template_tptr"]
            selected_kelas = str(form_data.get("kelas_kapal_id") or "")
            options = ['<option value="">Pilih kelas kapal...</option>']
            for kelas in kelas_records:
                selected_attr = ' selected="selected"' if str(kelas.id) == selected_kelas else ""
                options.append(
                    '<option value="{id}"{selected}>{name}</option>'.format(
                        id=kelas.id,
                        selected=selected_attr,
                        name=html.escape(kelas.name or "", quote=True),
                    )
                )
            template_options = []
            for template_key, meta in self._get_tptr_template_profiles().items():
                selected_attr = ' selected="selected"' if selected_template == template_key else ""
                template_options.append(
                    '<option value="{key}"{selected}>{label}</option>'.format(
                        key=html.escape(template_key, quote=True),
                        selected=selected_attr,
                        label=html.escape(meta["label"], quote=True),
                    )
                )

            hidden_project = ""
            if form_data.get("project_id"):
                hidden_project = (
                    '<input type="hidden" name="project_id" value="%s" />'
                    % html.escape(str(form_data.get("project_id")), quote=True)
                )

            has_project_symbol = bool(project and project.project_symbol)
            project_symbol_url = project._get_project_symbol_image_url() if has_project_symbol else ""
            symbol_note = (
                "Symbol aktif akan dipakai di cover sheet. Pilih file baru di kolom ini jika ingin mengganti symbol."
                if has_project_symbol
                else "Belum ada symbol. Preview akan muncul setelah file dipilih."
            )
            symbol_preview_style = "" if has_project_symbol else ' style="display:none;"'
            symbol_script_block = (
                "<script>"
                "(function(){"
                "var input=document.getElementById('wizard_project_symbol_input');"
                "var previewWrap=document.getElementById('wizard_project_symbol_meta');"
                "var preview=document.getElementById('wizard_project_symbol_preview');"
                "var note=document.getElementById('wizard_project_symbol_note');"
                "if(!input||!previewWrap||!preview||!note){return;}"
                "input.addEventListener('change',function(){"
                "var file=input.files&&input.files[0];"
                "if(!file){return;}"
                "note.textContent='Preview di bawah memakai file yang baru dipilih.';"
                "var reader=new FileReader();"
                "reader.onload=function(event){preview.src=event.target.result;previewWrap.style.display='flex';};"
                "reader.readAsDataURL(file);"
                "});"
                "})();"
                "</script>"
            )
            symbol_preview_block = (
                '<label class="wizard-symbol-uploader wizard-span-2">'
                '<span>Project Symbol (Opsional)</span>'
                '<input id="wizard_project_symbol_input" type="file" name="project_symbol" accept="image/*" />'
                '<div id="wizard_project_symbol_meta" class="wizard-symbol-inline"{symbol_preview_style}>'
                '<div class="wizard-symbol-thumb">'
                '<img id="wizard_project_symbol_preview" src="{symbol_src}" alt="Preview Project Symbol" />'
                "</div>"
                '<div class="wizard-symbol-inline-copy">'
                '<strong>{symbol_title}</strong>'
                '<small id="wizard_project_symbol_note">{symbol_note}</small>'
                "</div>"
                "</div>"
                "</label>"
                "{symbol_script_block}"
            ).format(
                symbol_preview_style=symbol_preview_style,
                symbol_src=html.escape(project_symbol_url, quote=True),
                symbol_title=html.escape("Symbol tersimpan" if has_project_symbol else "Preview Symbol", quote=True),
                symbol_note=html.escape(symbol_note, quote=True),
                symbol_script_block=symbol_script_block,
            )

            return (
                '<h2>Step 1: Data Kapal &amp; Proyek</h2>'
                '<p class="wizard-help">Simpan data dasar untuk membuka step berikutnya.</p>'
                '<form method="post" action="/tptr/cover-wizard/step1/save" enctype="multipart/form-data" class="wizard-form">'
                '<input type="hidden" name="csrf_token" value="{csrf}" />'
                "{hidden_project}"
                '<div class="wizard-template-inline">'
                '<div>'
                '<span class="wizard-template-inline-label">Template Dokumen</span>'
                '<strong>{selected_template_label}</strong>'
                '<small>{selected_footer_label}</small>'
                '</div>'
                '<span class="wizard-template-inline-note">Template bisa diubah dari dropdown di bawah.</span>'
                '</div>'
                '<div class="wizard-grid">'
                '<label><span>Template TPTR</span><select name="template_tptr" required>{template_options}</select></label>'
                '<label><span>Nama Kapal</span><input type="text" name="nama_kapal" required value="{nama_kapal}" /></label>'
                '<label><span>Nomor Proyek</span><input type="text" name="nomor_proyek" required value="{nomor_proyek}" /></label>'
                '<label><span>Kelas Kapal</span><select name="kelas_kapal_id" required>{kelas_options}</select></label>'
                '<label><span>Delegasi Pemilik</span><input type="text" name="delegasi_pemilik" required value="{delegasi_pemilik}" /></label>'
                '<label><span>Jenis Tes</span><select name="jenis_tes">'
                '<option value="hat"{hat_selected}>HAT</option>'
                '<option value="sat"{sat_selected}>SAT</option>'
                "</select></label>"
                "{symbol_preview_block}"
                "</div>"
                '<div class="wizard-actions"><button type="submit" class="wizard-btn wizard-btn-primary">Simpan &amp; Lanjut Step 2</button></div>'
                "</form>"
            ).format(
                csrf=html.escape(csrf_token, quote=True),
                hidden_project=hidden_project,
                selected_template_label=html.escape(
                    self._get_tptr_template_profile(selected_template).get("label", "RHIB"),
                    quote=True,
                ),
                selected_footer_label=html.escape(
                    self._get_tptr_template_profile(selected_template).get("footer_label", "-"),
                    quote=True,
                ),
                template_options="".join(template_options),
                nama_kapal=html.escape(form_data.get("nama_kapal") or "", quote=True),
                nomor_proyek=html.escape(form_data.get("nomor_proyek") or "", quote=True),
                kelas_options="".join(options),
                delegasi_pemilik=html.escape(form_data.get("delegasi_pemilik") or "", quote=True),
                hat_selected=' selected="selected"' if (form_data.get("jenis_tes") or "hat") == "hat" else "",
                sat_selected=' selected="selected"' if (form_data.get("jenis_tes") or "hat") == "sat" else "",
                symbol_preview_block=symbol_preview_block,
            )

        if not project:
            return (
                '<h2>Project belum tersedia</h2>'
                '<p class="wizard-help">Silakan isi Step 1 terlebih dahulu.</p>'
            )

        if step == 2:
            if not form_data:
                latest_lokasi = request.env["tptr.lokasi_kelas"].search(
                    [("kapal_id", "=", project.id)],
                    order="tanggal_input desc, id desc",
                    limit=1,
                )
                form_data = {
                    "lokasi_pengujian": latest_lokasi.lokasi_pengujian if latest_lokasi else "",
                    "note": latest_lokasi.note if latest_lokasi else "",
                    "sign_class": bool(latest_lokasi.sign_class) if latest_lokasi else False,
                    "sign_class_signature_filename": (
                        latest_lokasi.sign_class_signature_filename if latest_lokasi else ""
                    ),
                }
            sign_enabled = bool(form_data.get("sign_class"))
            sign_checked = " checked" if sign_enabled else ""
            signature_wrap_style = "" if sign_enabled else ' style="display:none;"'
            signature_filename = (form_data.get("sign_class_signature_filename") or "").strip()
            signature_filename_block = ""
            script_block = (
                "<script>"
                "(function(){"
                "var checkbox=document.getElementById('sign_class_checkbox');"
                "var wrapper=document.getElementById('sign_class_signature_wrap');"
                "var input=document.getElementById('sign_class_signature');"
                "if(!checkbox||!wrapper||!input){return;}"
                "var sync=function(){"
                "var enabled=checkbox.checked;"
                "wrapper.style.display=enabled?'flex':'none';"
                "input.required=enabled;"
                "if(!enabled){input.value='';}"
                "};"
                "checkbox.addEventListener('change',sync);"
                "sync();"
                "})();"
                "</script>"
            )
            if signature_filename:
                signature_filename_block = (
                    '<small class="wizard-inline-note">File dipilih sebelumnya: %s</small>'
                    % html.escape(signature_filename, quote=True)
                )
            return (
                '<h2>Step 2: Lokasi &amp; Kelas Pengujian</h2>'
                '<p class="wizard-help">Isi lokasi pengujian untuk project aktif.</p>'
                '<form method="post" action="/tptr/cover-wizard/step2/save" enctype="multipart/form-data" class="wizard-form">'
                '<input type="hidden" name="csrf_token" value="{csrf}" />'
                '<input type="hidden" name="project_id" value="{project_id}" />'
                '<div class="wizard-grid">'
                '<label><span>Lokasi Pengujian</span><input type="text" name="lokasi_pengujian" required value="{lokasi}" /></label>'
                '<label class="wizard-checkbox"><input id="sign_class_checkbox" type="checkbox" name="sign_class"{checked} /><span>Sign Class</span></label>'
                '<label id="sign_class_signature_wrap" class="wizard-span-2"{signature_wrap_style}>'
                '<span>Upload Tanda Tangan Class</span>'
                '<input id="sign_class_signature" type="file" name="sign_class_signature" accept="image/*" />'
                '<small class="wizard-inline-note">Upload file gambar tanda tangan Class (png/jpg/jpeg).</small>'
                "{signature_filename_block}"
                "</label>"
                '<label class="wizard-span-2"><span>Catatan</span><textarea name="note" rows="4">{note}</textarea></label>'
                "</div>"
                '<div class="wizard-actions"><button type="submit" class="wizard-btn wizard-btn-primary">Simpan &amp; Lanjut Step 3</button></div>'
                "</form>"
                "{script_block}"
            ).format(
                csrf=html.escape(csrf_token, quote=True),
                project_id=project.id,
                lokasi=html.escape(form_data.get("lokasi_pengujian") or "", quote=True),
                checked=sign_checked,
                signature_wrap_style=signature_wrap_style,
                signature_filename_block=signature_filename_block,
                script_block=script_block,
                note=html.escape(form_data.get("note") or "", quote=True),
            )

        if step == 3:
            if not form_data:
                latest_dokumen = request.env["tptr.dokumen_pendukung"].search(
                    [("tp_id", "=", project.id)],
                    order="tanggal_input desc, id desc",
                    limit=1,
                )
                template_profile = self._get_tptr_template_profile(project.template_tptr)
                form_data = {
                    "referensi_desain": (
                        latest_dokumen.referensi_desain
                        if latest_dokumen
                        else template_profile["drawing_document_name"]
                    ),
                    "dokumen_maker": (
                        latest_dokumen.dokumen_maker
                        if latest_dokumen
                        else template_profile["document_no"]
                    ),
                    "keterangan": latest_dokumen.keterangan if latest_dokumen else "",
                }
            return (
                '<h2>Step 3: Dokumen Pendukung</h2>'
                '<p class="wizard-help">Masukkan referensi dokumen yang dipakai pada pengujian.</p>'
                '<form method="post" action="/tptr/cover-wizard/step3/save" class="wizard-form">'
                '<input type="hidden" name="csrf_token" value="{csrf}" />'
                '<input type="hidden" name="project_id" value="{project_id}" />'
                '<div class="wizard-grid">'
                '<label><span>Referensi Desain</span><input type="text" name="referensi_desain" required value="{referensi_desain}" /></label>'
                '<label><span>Dokumen Maker</span><input type="text" name="dokumen_maker" required value="{dokumen_maker}" /></label>'
                '<label class="wizard-span-2"><span>Keterangan</span><textarea name="keterangan" rows="4">{keterangan}</textarea></label>'
                "</div>"
                '<div class="wizard-actions"><button type="submit" class="wizard-btn wizard-btn-primary">Simpan &amp; Lanjut Step 4</button></div>'
                "</form>"
            ).format(
                csrf=html.escape(csrf_token, quote=True),
                project_id=project.id,
                referensi_desain=html.escape(form_data.get("referensi_desain") or "", quote=True),
                dokumen_maker=html.escape(form_data.get("dokumen_maker") or "", quote=True),
                keterangan=html.escape(form_data.get("keterangan") or "", quote=True),
            )

        if step == 4:
            if not form_data:
                form_data = {
                    "body_test_related_project_no": project.body_test_related_project_no or "",
                    "body_contract_specification": project.body_contract_specification or "",
                    "body_delegate_name": project.body_delegate_name or project.delegasi_pemilik or "",
                    "body_pt_pal_name": project.body_pt_pal_name or "",
                    "body_delegate_signature_filename": project.body_delegate_signature_filename or "",
                    "body_pt_pal_signature_filename": project.body_pt_pal_signature_filename or "",
                    "body_delegate_signature_date": str(project.body_delegate_signature_date or ""),
                    "body_pt_pal_signature_date": str(project.body_pt_pal_signature_date or ""),
                }
            page5_labels = project._get_body_page5_labels()
            template_profile = self._get_tptr_template_profile(project.template_tptr)
            current_document_no = project.nomor_dokumen_utama or template_profile["document_no"]
            delegate_file = (form_data.get("body_delegate_signature_filename") or "").strip()
            pt_pal_file = (form_data.get("body_pt_pal_signature_filename") or "").strip()
            delegate_meta = []
            pt_pal_meta = []
            if delegate_file:
                delegate_meta.append("File: %s" % html.escape(delegate_file, quote=True))
            if form_data.get("body_delegate_signature_date"):
                delegate_meta.append("Tanggal: %s" % html.escape(form_data.get("body_delegate_signature_date"), quote=True))
            if pt_pal_file:
                pt_pal_meta.append("File: %s" % html.escape(pt_pal_file, quote=True))
            if form_data.get("body_pt_pal_signature_date"):
                pt_pal_meta.append("Tanggal: %s" % html.escape(form_data.get("body_pt_pal_signature_date"), quote=True))
            signature_script = (
                "<script>"
                "(function(){"
                "var bindPad=function(name){"
                "var canvas=document.getElementById(name+'_canvas');"
                "var hidden=document.getElementById(name+'_drawn');"
                "var clearBtn=document.getElementById(name+'_clear');"
                "if(!canvas||!hidden||!clearBtn){return;}"
                "var ctx=canvas.getContext('2d');"
                "var drawing=false;"
                "var ratio=window.devicePixelRatio||1;"
                "var rect=canvas.getBoundingClientRect();"
                "canvas.width=rect.width*ratio;canvas.height=rect.height*ratio;ctx.scale(ratio,ratio);"
                "ctx.lineWidth=2;ctx.lineCap='round';ctx.strokeStyle='#143b6b';"
                "var position=function(event){var point=event.touches&&event.touches.length?event.touches[0]:event;var box=canvas.getBoundingClientRect();return {x:point.clientX-box.left,y:point.clientY-box.top};};"
                "var save=function(){hidden.value=canvas.toDataURL('image/png');};"
                "var start=function(event){drawing=true;var pos=position(event);ctx.beginPath();ctx.moveTo(pos.x,pos.y);event.preventDefault&&event.preventDefault();};"
                "var move=function(event){if(!drawing){return;}var pos=position(event);ctx.lineTo(pos.x,pos.y);ctx.stroke();save();event.preventDefault&&event.preventDefault();};"
                "var stop=function(){drawing=false;};"
                "canvas.addEventListener('mousedown',start);canvas.addEventListener('mousemove',move);window.addEventListener('mouseup',stop);"
                "canvas.addEventListener('touchstart',start,{passive:false});canvas.addEventListener('touchmove',move,{passive:false});window.addEventListener('touchend',stop,{passive:false});"
                "clearBtn.addEventListener('click',function(){ctx.clearRect(0,0,canvas.width,canvas.height);hidden.value='';});"
                "};"
                "bindPad('delegate_signature');"
                "bindPad('pt_pal_signature');"
                "})();"
                "</script>"
            )
            return (
                '<h2>Step 4: Body TPTR Halaman 5</h2>'
                '<p class="wizard-help">Lengkapi data halaman pendahuluan body TPTR beserta acceptance signature.</p>'
                '<form method="post" action="/tptr/cover-wizard/step4/save" enctype="multipart/form-data" class="wizard-form">'
                '<input type="hidden" name="csrf_token" value="{csrf}" />'
                '<input type="hidden" name="project_id" value="{project_id}" />'
                '<section class="wizard-page5-summary">'
                '<article><span>Jenis Tes</span><strong>{test_prefix}</strong></article>'
                '<article><span>Template</span><strong>{template_label}</strong></article>'
                '<article><span>Nomor Proyek</span><strong>{project_no}</strong></article>'
                '<article><span>Nomor Dokumen</span><strong>{document_no}</strong></article>'
                '<article class="wide"><span>Heading Halaman 5</span><strong>{heading_main}</strong><small>{test_label}: {object_label}</small></article>'
                "</section>"
                '<div class="wizard-grid">'
                '<label class="wizard-span-2"><span>Pengujian untuk Nomor Proyek</span><input type="text" name="body_test_related_project_no" required value="{body_test_related_project_no}" /></label>'
                '<label class="wizard-span-2"><span>Spesifikasi Kontrak</span><textarea name="body_contract_specification" rows="4" required>{body_contract_specification}</textarea></label>'
                '<label><span>Name Delegate Team</span><input type="text" name="body_delegate_name" value="{body_delegate_name}" /></label>'
                '<label><span>Name PT PAL Indonesia</span><input type="text" name="body_pt_pal_name" value="{body_pt_pal_name}" /></label>'
                "</div>"
                '<section class="wizard-signature-grid">'
                '<article class="wizard-signature-card">'
                '<h3>{delegate_label}</h3>'
                '<p>Upload gambar atau tanda tangan langsung di canvas.</p>'
                '<label><span>Upload Tanda Tangan</span><input type="file" name="body_delegate_signature_file" accept="image/*" /></label>'
                '<div class="wizard-signature-pad-wrap">'
                '<canvas id="delegate_signature_canvas" class="wizard-signature-pad"></canvas>'
                '<input type="hidden" id="delegate_signature_drawn" name="body_delegate_signature_drawn" value="" />'
                '<button id="delegate_signature_clear" type="button" class="wizard-btn wizard-btn-soft">Bersihkan Canvas</button>'
                "</div>"
                '<small class="wizard-inline-note">{delegate_meta}</small>'
                "</article>"
                '<article class="wizard-signature-card">'
                '<h3>PT PAL Indonesia</h3>'
                '<p>Upload gambar atau tanda tangan langsung di canvas.</p>'
                '<label><span>Upload Tanda Tangan</span><input type="file" name="body_pt_pal_signature_file" accept="image/*" /></label>'
                '<div class="wizard-signature-pad-wrap">'
                '<canvas id="pt_pal_signature_canvas" class="wizard-signature-pad"></canvas>'
                '<input type="hidden" id="pt_pal_signature_drawn" name="body_pt_pal_signature_drawn" value="" />'
                '<button id="pt_pal_signature_clear" type="button" class="wizard-btn wizard-btn-soft">Bersihkan Canvas</button>'
                "</div>"
                '<small class="wizard-inline-note">{pt_pal_meta}</small>'
                "</article>"
                "</section>"
                '<div class="wizard-actions"><button type="submit" class="wizard-btn wizard-btn-primary">Simpan &amp; Lanjut Step 5</button></div>'
                "</form>"
                "{signature_script}"
            ).format(
                csrf=html.escape(csrf_token, quote=True),
                project_id=project.id,
                test_prefix=html.escape(page5_labels["test_prefix"], quote=True),
                template_label=html.escape(template_profile["label"], quote=True),
                project_no=html.escape(project.nomor_proyek or "-", quote=True),
                document_no=html.escape(current_document_no, quote=True),
                heading_main=html.escape(page5_labels["headline_main"], quote=True),
                test_label=html.escape(page5_labels["test_full_label"], quote=True),
                object_label=html.escape(page5_labels["object_label"], quote=True),
                body_test_related_project_no=html.escape(form_data.get("body_test_related_project_no") or "", quote=True),
                body_contract_specification=html.escape(form_data.get("body_contract_specification") or "", quote=True),
                body_delegate_name=html.escape(form_data.get("body_delegate_name") or "", quote=True),
                body_pt_pal_name=html.escape(form_data.get("body_pt_pal_name") or "", quote=True),
                delegate_label=html.escape(project.delegasi_pemilik or "Delegate Team", quote=True),
                delegate_meta="<br/>".join(delegate_meta) if delegate_meta else "Belum ada signature tersimpan.",
                pt_pal_meta="<br/>".join(pt_pal_meta) if pt_pal_meta else "Belum ada signature tersimpan.",
                signature_script=signature_script,
            )

        if step == 5:
            page6_defaults = project._get_body_page6_defaults()
            page6_static_rows = project._get_body_page6_static_rows()
            if not form_data:
                form_data = {
                    "body_supporting_reference": project.body_supporting_reference or page6_defaults["supporting_reference"],
                    "body_condition": project.body_condition or page6_defaults["condition"],
                    "body_time": project.body_time or page6_defaults["time"],
                }

            def _render_static_text(rows):
                blocks = []
                for row in rows:
                    parts = ["%s %s" % ((row.get("prefix") or "-").strip(), row.get("main") or "")]
                    if row.get("sub"):
                        parts.append(row.get("sub") or "")
                    blocks.append("\n".join(parts).strip())
                return "\n\n".join(blocks)

            return (
                '<h2>Step 5: Body TPTR Halaman 6</h2>'
                '<p class="wizard-help">Lengkapi referensi pendukung, kondisi, dan waktu. Bagian dokumen pendukung serta definisi pengujian mengikuti template.</p>'
                '<form method="post" action="/tptr/cover-wizard/step5/save" class="wizard-form">'
                '<input type="hidden" name="csrf_token" value="{csrf}" />'
                '<input type="hidden" name="project_id" value="{project_id}" />'
                '<div class="wizard-grid">'
                '<label class="wizard-span-2"><span>Dokumen Pendukung (Template)</span><textarea rows="7" readonly>{document_template_text}</textarea></label>'
                '<label class="wizard-span-2"><span>Referensi Pendukung</span><textarea name="body_supporting_reference" rows="4" required>{body_supporting_reference}</textarea></label>'
                '<label class="wizard-span-2"><span>Kondisi</span><textarea name="body_condition" rows="8" required>{body_condition}</textarea></label>'
                '<label class="wizard-span-2"><span>Waktu</span><textarea name="body_time" rows="4" required>{body_time}</textarea></label>'
                '<label class="wizard-span-2"><span>Definisi Pengujian (Template)</span><textarea rows="5" readonly>{definition_template_text}</textarea></label>'
                "</div>"
                '<div class="wizard-actions"><button type="submit" class="wizard-btn wizard-btn-primary">Simpan &amp; Lanjut Step 6</button></div>'
                "</form>"
            ).format(
                csrf=html.escape(csrf_token, quote=True),
                project_id=project.id,
                document_template_text=html.escape(_render_static_text(page6_static_rows["document_rows"]), quote=True),
                body_supporting_reference=html.escape(form_data.get("body_supporting_reference") or "", quote=True),
                body_condition=html.escape(form_data.get("body_condition") or "", quote=True),
                body_time=html.escape(form_data.get("body_time") or "", quote=True),
                definition_template_text=html.escape(_render_static_text(page6_static_rows["definition_rows"]), quote=True),
            )

        if step == 6:
            if not form_data:
                member_lines = [line.strip() for line in (project.test_record_general_members or "").replace("\r", "").split("\n") if line.strip()]
                while len(member_lines) < 4:
                    member_lines.append("")
                form_data = {
                    "test_record_general_date": str(project.test_record_general_date or ""),
                    "test_record_general_place": project.test_record_general_place or "",
                    "test_record_general_team_leader": project.test_record_general_team_leader or "",
                    "test_record_general_member_1": member_lines[0],
                    "test_record_general_member_2": member_lines[1],
                    "test_record_general_member_3": member_lines[2],
                    "test_record_general_member_4": member_lines[3],
                    "test_record_general_delegate_name": project.test_record_general_delegate_name or "",
                    "test_record_general_class_surveyor_name": project.test_record_general_class_surveyor_name or "",
                }

            is_davits = (project.template_tptr == "davits_rhib")
            surveyor_style = "" if is_davits else ' style="display:none;"'
            surveyor_required = " required" if is_davits else ""
            cover_profile = self._get_tptr_template_profile(project.template_tptr)
            project_name_label = cover_profile.get("label") or "FRIGATE 140 M"

            return (
                '<h2>Step 6: Test Record Halaman 7</h2>'
                '<p class="wizard-help">Lengkapi data pengujian (Tanggal, Tempat, Pelaksana, dan Anggota) untuk Halaman 7 Test Record.</p>'
                '<form method="post" action="/tptr/cover-wizard/step6/save" class="wizard-form">'
                '<input type="hidden" name="csrf_token" value="{csrf}" />'
                '<input type="hidden" name="project_id" value="{project_id}" />'
                '<div class="wizard-grid">'
                '<label><span>Tanggal</span><input type="date" name="test_record_general_date" required value="{date}" /></label>'
                '<label><span>Tempat</span><input type="text" name="test_record_general_place" required value="{place}" /></label>'
                '<label class="wizard-span-2"><span>Ketua Tim PT PAL</span><input type="text" name="test_record_general_team_leader" required value="{team_leader}" /></label>'
                '<label><span>Anggota 1</span><input type="text" name="test_record_general_member_1" required value="{member_1}" /></label>'
                '<label><span>Anggota 2</span><input type="text" name="test_record_general_member_2" value="{member_2}" /></label>'
                '<label><span>Anggota 3</span><input type="text" name="test_record_general_member_3" value="{member_3}" /></label>'
                '<label><span>Anggota 4</span><input type="text" name="test_record_general_member_4" value="{member_4}" /></label>'
                '<label class="wizard-span-2"><span>Satgas {project_name}</span><input type="text" name="test_record_general_delegate_name" required value="{delegate_name}" /></label>'
                '<label id="class_surveyor_wrap" class="wizard-span-2"{surveyor_style}><span>Biro Klasifikasi {class_name}</span><input id="class_surveyor_input" type="text" name="test_record_general_class_surveyor_name"{surveyor_required} value="{class_surveyor_name}" /></label>'
                "</div>"
                '<div class="wizard-actions"><button type="submit" class="wizard-btn wizard-btn-primary">Simpan &amp; Lanjut Step 7</button></div>'
                "</form>"
            ).format(
                csrf=html.escape(csrf_token, quote=True),
                project_id=project.id,
                date=html.escape(form_data.get("test_record_general_date") or "", quote=True),
                place=html.escape(form_data.get("test_record_general_place") or "", quote=True),
                team_leader=html.escape(form_data.get("test_record_general_team_leader") or "", quote=True),
                member_1=html.escape(form_data.get("test_record_general_member_1") or "", quote=True),
                member_2=html.escape(form_data.get("test_record_general_member_2") or "", quote=True),
                member_3=html.escape(form_data.get("test_record_general_member_3") or "", quote=True),
                member_4=html.escape(form_data.get("test_record_general_member_4") or "", quote=True),
                project_name=html.escape(project_name_label, quote=True),
                delegate_name=html.escape(form_data.get("test_record_general_delegate_name") or "", quote=True),
                class_name=html.escape(project.kelas_kapal or "LR", quote=True),
                surveyor_style=surveyor_style,
                surveyor_required=surveyor_required,
                class_surveyor_name=html.escape(form_data.get("test_record_general_class_surveyor_name") or "", quote=True),
            )

        if step == 7:
            is_davits = (project.template_tptr == "davits_rhib")
            if not form_data:
                form_data = {}
            
            defaults = {
                "davit_maker": project.davit_maker or "PT ATHIRA MARITIM INDONESIA",
                "davit_model": project.davit_model or "ATH-RHIB-50KN",
                "davit_type": project.davit_type or "RHIB50-6.1M-SL",
                "davit_hoisting_speed": project.davit_hoisting_speed or "10 meter / menit",
                "davit_lifting_height": project.davit_lifting_height or "15 Meter",
                "davit_swl": project.davit_swl or "50 KN (5,1 TON)",
                "davit_number": project.davit_number or "2 (DUA) UNIT / (units)",
                "prep_davit_inspector": project.prep_davit_inspector or "ok",
                "prep_davit_attendance": project.prep_davit_attendance or "ok",
                "prep_davit_document": project.prep_davit_document or "ok",
                "rhib_maker": project.rhib_maker or "TRISETIA CIPTA PERSADA",
                "rhib_loa": project.rhib_loa or "8,50 Meter",
                "rhib_hull_length": project.rhib_hull_length or "7,750 Meter",
                "rhib_breadth": project.rhib_breadth or "3,00 Meter",
                "rhib_hull_height": project.rhib_hull_height or "1,35 Meter",
                "rhib_draft": project.rhib_draft or "0.50 Meter",
                "rhib_engine": project.rhib_engine or "YAMAHA F2000BETX/FL200BETX",
                "rhib_number": project.rhib_number or "2 (DUA) UNIT / 2(TWO) units",
                "rhib_max_speed": project.rhib_max_speed or "35,00 knots",
                "rhib_cruising_speed": project.rhib_cruising_speed or "18.00 knots",
                "rhib_capacity": project.rhib_capacity or "12 persons",
                "rhib_boat_weight": project.rhib_boat_weight or "2260 kg",
                "rhib_total_weight": project.rhib_total_weight or "3960 kg",
                "rhib_assumed_weight": project.rhib_assumed_weight or "3960 kg",
                "rhib_unit_count": project.rhib_unit_count or "2 (DUA) UNIT / (units)",
            }
            for k, v in defaults.items():
                if k not in form_data:
                    form_data[k] = v

            # Dynamic equipment rendering
            equip_list = project._get_peralatan_list()
            if form_data and "equip_name_id[]" in form_data:
                equip_names_id = form_data.get("equip_name_id[]") or []
                equip_names_en = form_data.get("equip_name_en[]") or []
                equip_rows = list(zip(equip_names_id, equip_names_en))
            else:
                equip_rows = [(e.name_id, e.name_en) for e in equip_list]

            if not equip_rows:
                equip_rows = [
                    ('PERALATAN KOMUNIKASI.', '(Communication Device (Handy Talky).)'),
                    ('PENGUKUR WAKTU.', '(Stopwatch.)'),
                    ('ALAT KESELAMATAN.', '(Safety Utility.)')
                ]

            rows_html = []
            for name_id, name_en in equip_rows:
                rows_html.append(
                    '<div class="equipment-row-item" style="grid-column: span 1;">'
                    f'<input type="text" name="equip_name_id[]" required placeholder="Contoh: PENGUKUR WAKTU." value="{html.escape(name_id or "", quote=True)}" style="width:100%; min-height:40px; border:1px solid #c2d1e7; border-radius:8px; padding:0 10px;" />'
                    '</div>'
                    '<div class="equipment-row-item" style="grid-column: span 1;">'
                    f'<input type="text" name="equip_name_en[]" required placeholder="Contoh: (Stopwatch.)" value="{html.escape(name_en or "", quote=True)}" style="width:100%; min-height:40px; border:1px solid #c2d1e7; border-radius:8px; padding:0 10px;" />'
                    '</div>'
                    '<div class="equipment-row-item" style="grid-column: span 1;">'
                    '<button type="button" class="wizard-btn wizard-btn-danger" onclick="removeEquipmentRow(this)" style="min-height:40px; padding: 0 16px;">Hapus</button>'
                    '</div>'
                )
            equipment_rows_html = "".join(rows_html)

            # Equipment dynamic layout section with script
            equipment_section_html = (
                '<h3 style="margin-top:28px;">Peralatan yang Digunakan</h3>'
                '<p class="wizard-help">Lengkapi daftar peralatan yang digunakan untuk pengujian. Anda dapat menambah atau menghapus baris secara dinamis.</p>'
                '<div id="equipment_container" style="display: grid; grid-template-columns: 1fr 1fr auto; gap: 12px; align-items: end;">'
                '<div style="font-weight: 700; color: #1d4c90;">Peralatan (Indonesia)</div>'
                '<div style="font-weight: 700; color: #1d4c90;">Peralatan (Inggris)</div>'
                '<div></div>'
                f'{equipment_rows_html}'
                '</div>'
                '<div style="margin-top: 14px;">'
                '<button type="button" class="wizard-btn wizard-btn-soft" onclick="addEquipmentRow(\'\', \'\')">+ Tambah Peralatan</button>'
                '</div>'
                '<script>'
                'function addEquipmentRow(nameId, nameEn) {'
                '    const container = document.getElementById("equipment_container");'
                '    '
                '    const idInputWrap = document.createElement("div");'
                '    idInputWrap.className = "equipment-row-item";'
                '    idInputWrap.style.gridColumn = "span 1";'
                '    idInputWrap.innerHTML = `<input type="text" name="equip_name_id[]" required placeholder="Contoh: PENGUKUR WAKTU." value="${nameId}" style="width:100%; min-height:40px; border:1px solid #c2d1e7; border-radius:8px; padding:0 10px;" />`;'
                '    '
                '    const enInputWrap = document.createElement("div");'
                '    enInputWrap.className = "equipment-row-item";'
                '    enInputWrap.style.gridColumn = "span 1";'
                '    enInputWrap.innerHTML = `<input type="text" name="equip_name_en[]" required placeholder="Contoh: (Stopwatch.)" value="${nameEn}" style="width:100%; min-height:40px; border:1px solid #c2d1e7; border-radius:8px; padding:0 10px;" />`;'
                '    '
                '    const deleteBtnWrap = document.createElement("div");'
                '    deleteBtnWrap.className = "equipment-row-item";'
                '    deleteBtnWrap.style.gridColumn = "span 1";'
                '    deleteBtnWrap.innerHTML = `<button type="button" class="wizard-btn wizard-btn-danger" onclick="removeEquipmentRow(this)" style="min-height:40px; padding: 0 16px;">Hapus</button>`;'
                '    '
                '    container.appendChild(idInputWrap);'
                '    container.appendChild(enInputWrap);'
                '    container.appendChild(deleteBtnWrap);'
                '}'
                'function removeEquipmentRow(btn) {'
                '    const container = document.getElementById("equipment_container");'
                '    const items = Array.from(container.querySelectorAll(".equipment-row-item"));'
                '    const index = items.indexOf(btn.parentElement);'
                '    const rowStartIndex = Math.floor(index / 3) * 3;'
                '    if (items.length <= 3) {'
                '        alert("Minimal harus ada 1 peralatan yang digunakan.");'
                '        return;'
                '    }'
                '    items[rowStartIndex].remove();'
                '    items[rowStartIndex + 1].remove();'
                '    items[rowStartIndex + 2].remove();'
                '}'
                '</script>'
            )

            if is_davits:
                return (
                    '<h2>Step 7: Test Record Spesifikasi &amp; Peralatan (DAVITS)</h2>'
                    '<p class="wizard-help">Lengkapi data spesifikasi teknis Davit dan daftar peralatan yang digunakan.</p>'
                    '<form method="post" action="/tptr/cover-wizard/step7/save" class="wizard-form">'
                    '<input type="hidden" name="csrf_token" value="{csrf}" />'
                    '<input type="hidden" name="project_id" value="{project_id}" />'
                    '<h3>Spesifikasi Teknis Davit</h3>'
                    '<div class="wizard-grid">'
                    '<label><span>Pembuat (Maker)</span><input type="text" name="davit_maker" required value="{davit_maker}" /></label>'
                    '<label><span>Model</span><input type="text" name="davit_model" required value="{davit_model}" /></label>'
                    '<label><span>Type</span><input type="text" name="davit_type" required value="{davit_type}" /></label>'
                    '<label><span>Kecepatan Angkat</span><input type="text" name="davit_hoisting_speed" required value="{davit_hoisting_speed}" /></label>'
                    '<label><span>Ketinggian Angkat</span><input type="text" name="davit_lifting_height" required value="{davit_lifting_height}" /></label>'
                    '<label><span>Safety Weight Load (SWL)</span><input type="text" name="davit_swl" required value="{davit_swl}" /></label>'
                    '<label class="wizard-span-2"><span>Jumlah</span><input type="text" name="davit_number" required value="{davit_number}" /></label>'
                    "</div>"
                    '__EQUIPMENT__'
                    '<div class="wizard-actions" style="margin-top:24px;"><button type="submit" class="wizard-btn wizard-btn-primary">Simpan &amp; Lanjut Step 8</button></div>'
                    "</form>"
                ).format(
                    csrf=html.escape(csrf_token, quote=True),
                    project_id=project.id,
                    davit_maker=html.escape(form_data.get("davit_maker") or "", quote=True),
                    davit_model=html.escape(form_data.get("davit_model") or "", quote=True),
                    davit_type=html.escape(form_data.get("davit_type") or "", quote=True),
                    davit_hoisting_speed=html.escape(form_data.get("davit_hoisting_speed") or "", quote=True),
                    davit_lifting_height=html.escape(form_data.get("davit_lifting_height") or "", quote=True),
                    davit_swl=html.escape(form_data.get("davit_swl") or "", quote=True),
                    davit_number=html.escape(form_data.get("davit_number") or "", quote=True),
                ).replace('__EQUIPMENT__', equipment_section_html)
            else:
                return (
                    '<h2>Step 7: Test Record Spesifikasi &amp; Persiapan Uji (RHIB)</h2>'
                    '<p class="wizard-help">Lengkapi data spesifikasi teknis Rigid Hull Inflatable Boat (RHIB) dan daftar peralatan yang digunakan untuk halaman test record.</p>'
                    '<form method="post" action="/tptr/cover-wizard/step7/save" class="wizard-form">'
                    '<input type="hidden" name="csrf_token" value="{csrf}" />'
                    '<input type="hidden" name="project_id" value="{project_id}" />'
                    '<h3>Spesifikasi Teknis RHIB</h3>'
                    '<div class="wizard-grid">'
                    '<label><span>Pembuat (Maker)</span><input type="text" name="rhib_maker" required value="{rhib_maker}" /></label>'
                    '<label><span>Panjang LOA</span><input type="text" name="rhib_loa" required value="{rhib_loa}" /></label>'
                    '<label><span>Panjang Lambung (L Hull)</span><input type="text" name="rhib_hull_length" required value="{rhib_hull_length}" /></label>'
                    '<label><span>Lebar (Breadth) B Moulded</span><input type="text" name="rhib_breadth" required value="{rhib_breadth}" /></label>'
                    '<label><span>Tinggi Lambung Height hull H</span><input type="text" name="rhib_hull_height" required value="{rhib_hull_height}" /></label>'
                    '<label><span>Serat Draft T</span><input type="text" name="rhib_draft" required value="{rhib_draft}" /></label>'
                    '<label class="wizard-span-2"><span>Mesin (Engine)</span><input type="text" name="rhib_engine" required value="{rhib_engine}" /></label>'
                    '<label><span>Jumlah (Number)</span><input type="text" name="rhib_number" required value="{rhib_number}" /></label>'
                    '<label><span>Kecepatan Maksimum</span><input type="text" name="rhib_max_speed" required value="{rhib_max_speed}" /></label>'
                    '<label><span>Kecepatan Berlayar</span><input type="text" name="rhib_cruising_speed" required value="{rhib_cruising_speed}" /></label>'
                    '<label><span>Kapasitas</span><input type="text" name="rhib_capacity" required value="{rhib_capacity}" /></label>'
                    '<label><span>Berat Sekoci</span><input type="text" name="rhib_boat_weight" required value="{rhib_boat_weight}" /></label>'
                    '<label><span>Berat Total</span><input type="text" name="rhib_total_weight" required value="{rhib_total_weight}" /></label>'
                    '<label><span>Asumsi Penumpang 12 Orang</span><input type="text" name="rhib_assumed_weight" required value="{rhib_assumed_weight}" /></label>'
                    '<label><span>Jumlah Unit</span><input type="text" name="rhib_unit_count" required value="{rhib_unit_count}" /></label>'
                    "</div>"
                    '__EQUIPMENT__'
                    '<div class="wizard-actions" style="margin-top:24px;"><button type="submit" class="wizard-btn wizard-btn-primary">Simpan &amp; Lanjut Step 8</button></div>'
                    "</form>"
                ).format(
                    csrf=html.escape(csrf_token, quote=True),
                    project_id=project.id,
                    rhib_maker=html.escape(form_data.get("rhib_maker") or "", quote=True),
                    rhib_loa=html.escape(form_data.get("rhib_loa") or "", quote=True),
                    rhib_hull_length=html.escape(form_data.get("rhib_hull_length") or "", quote=True),
                    rhib_breadth=html.escape(form_data.get("rhib_breadth") or "", quote=True),
                    rhib_hull_height=html.escape(form_data.get("rhib_hull_height") or "", quote=True),
                    rhib_draft=html.escape(form_data.get("rhib_draft") or "", quote=True),
                    rhib_engine=html.escape(form_data.get("rhib_engine") or "", quote=True),
                    rhib_number=html.escape(form_data.get("rhib_number") or "", quote=True),
                    rhib_max_speed=html.escape(form_data.get("rhib_max_speed") or "", quote=True),
                    rhib_cruising_speed=html.escape(form_data.get("rhib_cruising_speed") or "", quote=True),
                    rhib_capacity=html.escape(form_data.get("rhib_capacity") or "", quote=True),
                    rhib_boat_weight=html.escape(form_data.get("rhib_boat_weight") or "", quote=True),
                    rhib_total_weight=html.escape(form_data.get("rhib_total_weight") or "", quote=True),
                    rhib_assumed_weight=html.escape(form_data.get("rhib_assumed_weight") or "", quote=True),
                    rhib_unit_count=html.escape(form_data.get("rhib_unit_count") or "", quote=True),
                ).replace('__EQUIPMENT__', equipment_section_html)

        if step == 8:
            is_rhib = (project.template_tptr != "davits_rhib")
            if not is_rhib:
                if not form_data:
                    form_data = {}

                prep_items = [
                    ("prep_davit_inspector", 
                     "INSPEKTUR QUALITY ASSURANCE PT PAL MELAPORKAN KESIAPAN DARI PERALATAN DAVITS.",
                     "Quality assurance inspector of PT PAL reports on the readiness of the Davits equipment's"),
                    ("prep_davit_attendance",
                     "KEHADIRAN TIM PENGUJIAN.",
                     "Attendance of test team."),
                    ("prep_davit_document",
                     "DOKUMEN PENDUKUNG SESUAI ITEM NO. 3 PADA TEST PROSEDUR TELAH TERSEDIA.",
                     "Document for the test according to item no. 3 in the test procedure are available."),
                    ("prep_davit_equipment",
                     "PERALATAN YANG DIGUNAKAN SESUAI ITEM NO. 3 PADA TEST RECORD TELAH TERSEDIA.",
                     "Equipment to be used according to item no. 3 in the test record are available.")
                ]
                
                test_items = [
                    ("davit_test_load",
                     "UJI BEBAN STATIS / DINAMIS DAVIT.",
                     "Static / dynamic load test of Davits."),
                    ("davit_test_lifting",
                     "UJI FUNGSI ANGKAT BEBAN (LIFTING TEST).",
                     "Lifting load function test."),
                    ("davit_test_lowering",
                     "UJI FUNGSI TURUN BEBAN (LOWERING TEST).",
                     "Lowering load function test.")
                ]

                safe_items = [
                    ("davit_safe_relief_valve",
                     "KATUP PELEPAS TEKANAN (PRESSURE RELIEF VALVE) PADA PANEL UTAMA SISTEM HIDROLIK DI-SET SESUAI SPESIFIKASI.",
                     "Pressure relief valve on hydraulic system main panel is set according to specification."),
                    ("davit_safe_locking",
                     "SISTEM PENGUNCIAN MEKANIS SILINDER DAVIT (CYLINDER MECHANICAL LOCKING SYSTEM) BEKERJA BAIK.",
                     "Davit cylinder mechanical locking system works properly."),
                    ("davit_safe_holding_valve",
                     "KATUP PENAHAN BEBAN (LOAD HOLDING VALVE / COUNTERBALANCE VALVE) BERFUNGSI MENCEGAH BEBAN JATUH.",
                     "Load holding valve / counterbalance valve functions to prevent load drop."),
                    ("davit_safe_stop_limit",
                     "HOOK STOP LIMIT ATAS / LIMIT SWITCH MEMBATASI GERAKAN MAKSIMUM ANGKAT DENGAN AMAN.",
                     "Top hook stop limit / limit switch limits maximum hoist motion safely."),
                    ("davit_safe_power_fail_brake",
                     "REM PENGAMAN BEKERJA KETIKA DAYA LISTRIK TIBA-TIBA MATI (POWER FAILURE BRAKE SAFELY APPLIED).",
                     "Safety brake operates when power supply is suddenly cut off."),
                    ("davit_safe_space_heater",
                     "PEMANAS MOTOR & TERMOSTAT (SPACE HEATER & THERMOSTAT) DI PANEL OPERASI BERFUNGSI BAIK.",
                     "Motor space heater & thermostat in operation panel functions properly.")
                ]

                panel_items = [
                    ("davit_panel_alarm",
                     "ALARM SUARA & VISUAL (AUDIBLE & VISUAL ALARM) BERFUNGSI SAAT TERJADI ABNORMALITAS ATAU PENGOPERASIAN.",
                     "Audible & visual alarm functions during abnormality or operation."),
                    ("davit_panel_integration",
                     "INDIKASI REMOTE & POMPA (REMOTE STATUS & PUMP RUNNING INDICATION) MENUNJUKKAN STATUS AKTIF DENGAN BENAR.",
                     "Remote status & pump running indication correctly shows active status.")
                ]

                def render_checklist_table(items, starting_no=1):
                    rows = []
                    for i, (field_name, text_id, text_en) in enumerate(items):
                        val = form_data.get(field_name) or getattr(project, field_name) or "ok"
                        ok_checked = ' checked' if val == 'ok' else ''
                        not_checked = ' checked' if val == 'not_ok' else ''
                        
                        rows.append(
                            f'<tr>'
                            f'<td style="padding:12px; border:1px solid #b7c9df;">'
                            f'<strong style="color: #1d4c90;">{starting_no + i}. {html.escape(text_id)}</strong><br/>'
                            f'<small style="color:#557092; font-style:italic;">{html.escape(text_en)}</small>'
                            f'</td>'
                            f'<td style="padding:12px; border:1px solid #b7c9df; text-align:center; vertical-align:middle; width:90px;">'
                            f'<input type="radio" name="{field_name}" value="ok"{ok_checked} required style="transform: scale(1.2); cursor: pointer;" />'
                            f'</td>'
                            f'<td style="padding:12px; border:1px solid #b7c9df; text-align:center; vertical-align:middle; width:90px;">'
                            f'<input type="radio" name="{field_name}" value="not_ok"{not_checked} style="transform: scale(1.2); cursor: pointer;" />'
                            f'</td>'
                            f'</tr>'
                        )
                    return (
                        '<table class="wizard-template-table" style="width:100%; border-collapse:collapse; border:1px solid #b7c9df; font-size:14px; margin-top:12px; background: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">'
                        '<thead>'
                        '<tr style="background:#1d4c90; color:#ffffff; font-size: 15px;">'
                        '<th style="padding:12px; border:1px solid #b7c9df; text-align:left;">Item Pemeriksaan</th>'
                        '<th style="padding:12px; border:1px solid #b7c9df; width:90px; text-align:center;">OK</th>'
                        '<th style="padding:12px; border:1px solid #b7c9df; width:90px; text-align:center;">NOT OK</th>'
                        '</tr>'
                        '</thead>'
                        '<tbody>'
                        f'{"".join(rows)}'
                        '</tbody>'
                        '</table>'
                    )

                time_lift = form_data.get("davit_hoist_time_lift") or project.davit_hoist_time_lift or "1.5"
                press_lift = form_data.get("davit_hoist_press_lift") or project.davit_hoist_press_lift or "140"
                time_lower = form_data.get("davit_hoist_time_lower") or project.davit_hoist_time_lower or "1.8"
                press_lower = form_data.get("davit_hoist_press_lower") or project.davit_hoist_press_lower or "150"

                hoisting_table_html = (
                    '<table class="wizard-template-table" style="width:100%; border-collapse:collapse; border:1px solid #b7c9df; font-size:14px; margin-top:12px; background: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">'
                    '<thead>'
                    '<tr style="background:#1d4c90; color:#ffffff; font-size: 15px;">'
                    '<th style="padding:12px; border:1px solid #b7c9df; text-align:left;">Uraian Pengujian <small style="display:block; font-style:italic; font-weight:normal; color:#e0e8f5;">(Test Description)</small></th>'
                    '<th style="padding:12px; border:1px solid #b7c9df; width:180px; text-align:center;">Waktu (menit) <small style="display:block; font-style:italic; font-weight:normal; color:#e0e8f5;">(Time - minutes)</small></th>'
                    '<th style="padding:12px; border:1px solid #b7c9df; width:180px; text-align:center;">Tekanan (kg/cm2) <small style="display:block; font-style:italic; font-weight:normal; color:#e0e8f5;">(Pressure - kg/cm2)</small></th>'
                    '</tr>'
                    '</thead>'
                    '<tbody>'
                    '<tr>'
                    '<td style="padding:12px; border:1px solid #b7c9df;">'
                    '<strong style="color: #1d4c90;">- Waktu Pengangkatan Sekoci</strong><br/>'
                    '<small style="color:#557092; font-style:italic;">(Lifting time of boat)</small>'
                    '</td>'
                    '<td style="padding:12px; border:1px solid #b7c9df; text-align:center;">'
                    f'<input type="text" name="davit_hoist_time_lift" value="{html.escape(str(time_lift))}" required style="width:100%; max-width:120px; text-align:center; min-height:36px; border:1px solid #c2d1e7; border-radius:6px; padding:0 8px;" />'
                    '</td>'
                    '<td style="padding:12px; border:1px solid #b7c9df; text-align:center;">'
                    f'<input type="text" name="davit_hoist_press_lift" value="{html.escape(str(press_lift))}" required style="width:100%; max-width:120px; text-align:center; min-height:36px; border:1px solid #c2d1e7; border-radius:6px; padding:0 8px;" />'
                    '</td>'
                    '</tr>'
                    '<tr>'
                    '<td style="padding:12px; border:1px solid #b7c9df;">'
                    '<strong style="color: #1d4c90;">- Waktu Penurunan Sekoci</strong><br/>'
                    '<small style="color:#557092; font-style:italic;">(Lowering time of boat)</small>'
                    '</td>'
                    '<td style="padding:12px; border:1px solid #b7c9df; text-align:center;">'
                    f'<input type="text" name="davit_hoist_time_lower" value="{html.escape(str(time_lower))}" required style="width:100%; max-width:120px; text-align:center; min-height:36px; border:1px solid #c2d1e7; border-radius:6px; padding:0 8px;" />'
                    '</td>'
                    '<td style="padding:12px; border:1px solid #b7c9df; text-align:center;">'
                    f'<input type="text" name="davit_hoist_press_lower" value="{html.escape(str(press_lower))}" required style="width:100%; max-width:120px; text-align:center; min-height:36px; border:1px solid #c2d1e7; border-radius:6px; padding:0 8px;" />'
                    '</td>'
                    '</tr>'
                    '</tbody>'
                    '</table>'
                )

                prep_table = render_checklist_table(prep_items, 1)
                test_table = render_checklist_table(test_items, 5)
                safe_table = render_checklist_table(safe_items, 8)
                panel_table = render_checklist_table(panel_items, 14)

                cat_list = project._get_catatan_list()
                if form_data and "catatan_remark[]" in form_data:
                    catatan_remarks = form_data.get("catatan_remark[]") or []
                    catatan_actions = form_data.get("catatan_action[]") or []
                    catatan_rows = list(zip(catatan_remarks, catatan_actions))
                else:
                    catatan_rows = [(c.remark or "", c.action or "") for c in cat_list]
                
                if not catatan_rows:
                    catatan_rows = [("", "")]
                
                cat_rows_html = []
                for remark, action in catatan_rows:
                    cat_rows_html.append(
                        '<div class="catatan-row-item" style="grid-column: span 1;">'
                        f'<input type="text" name="catatan_remark[]" placeholder="Contoh: SEMUA SISTEM BERFUNGSI BAIK." value="{html.escape(remark, quote=True)}" style="width:100%; min-height:40px; border:1px solid #c2d1e7; border-radius:8px; padding:0 10px;" />'
                        '</div>'
                        '<div class="catatan-row-item" style="grid-column: span 1;">'
                        f'<input type="text" name="catatan_action[]" placeholder="Contoh: DISETUJUI." value="{html.escape(action, quote=True)}" style="width:100%; min-height:40px; border:1px solid #c2d1e7; border-radius:8px; padding:0 10px;" />'
                        '</div>'
                        '<div class="catatan-row-item" style="grid-column: span 1;">'
                        '<button type="button" class="wizard-btn wizard-btn-danger" onclick="removeCatatanRow(this)" style="min-height:40px; padding: 0 16px;">Hapus</button>'
                        '</div>'
                    )
                catatan_rows_html = "".join(cat_rows_html)

                catatan_section_html = (
                    '<h3 style="margin-top:28px;">6. CATATAN (Remark)</h3>'
                    '<p class="wizard-help">Lengkapi catatan/remark hasil pengujian beserta aksi/action jika ada. Anda dapat menambah atau menghapus baris secara dinamis.</p>'
                    '<div id="catatan_container" style="display: grid; grid-template-columns: 1fr 1fr auto; gap: 12px; align-items: end;">'
                    '<div style="font-weight: 700; color: #1d4c90;">Catatan (Remark)</div>'
                    '<div style="font-weight: 700; color: #1d4c90;">Aksi (Action)</div>'
                    '<div></div>'
                    f'{catatan_rows_html}'
                    '</div>'
                    '<div style="margin-top: 14px;">'
                    '<button type="button" class="wizard-btn wizard-btn-soft" onclick="addCatatanRow(\'\', \'\')">+ Tambah Catatan</button>'
                    '</div>'
                    '<script>'
                    'function addCatatanRow(remark, action) {'
                    '    const container = document.getElementById("catatan_container");'
                    '    '
                    '    const idInputWrap = document.createElement("div");'
                    '    idInputWrap.className = "catatan-row-item";'
                    '    idInputWrap.style.gridColumn = "span 1";'
                    '    idInputWrap.innerHTML = `<input type="text" name="catatan_remark[]" placeholder="Contoh: SEMUA SISTEM BERFUNGSI BAIK." value="${remark}" style="width:100%; min-height:40px; border:1px solid #c2d1e7; border-radius:8px; padding:0 10px;" />`;'
                    '    '
                    '    const enInputWrap = document.createElement("div");'
                    '    enInputWrap.className = "catatan-row-item";'
                    '    enInputWrap.style.gridColumn = "span 1";'
                    '    enInputWrap.innerHTML = `<input type="text" name="catatan_action[]" placeholder="Contoh: DISETUJUI." value="${action}" style="width:100%; min-height:40px; border:1px solid #c2d1e7; border-radius:8px; padding:0 10px;" />`;'
                    '    '
                    '    const deleteBtnWrap = document.createElement("div");'
                    '    deleteBtnWrap.className = "catatan-row-item";'
                    '    deleteBtnWrap.style.gridColumn = "span 1";'
                    '    deleteBtnWrap.innerHTML = `<button type="button" class="wizard-btn wizard-btn-danger" onclick="removeCatatanRow(this)" style="min-height:40px; padding: 0 16px;">Hapus</button>`;'
                    '    '
                    '    container.appendChild(idInputWrap);'
                    '    container.appendChild(enInputWrap);'
                    '    container.appendChild(deleteBtnWrap);'
                    '}'
                    'function removeCatatanRow(btn) {'
                    '    const container = document.getElementById("catatan_container");'
                    '    const items = Array.from(container.querySelectorAll(".catatan-row-item"));'
                    '    const index = items.indexOf(btn.parentElement);'
                    '    const rowStartIndex = Math.floor(index / 3) * 3;'
                    '    if (items.length <= 3) {'
                    '        alert("Minimal harus ada 1 baris catatan (boleh dikosongkan).");'
                    '        return;'
                    '    }'
                    '    items[rowStartIndex].remove();'
                    '    items[rowStartIndex + 1].remove();'
                    '    items[rowStartIndex + 2].remove();'
                    '}'
                    '</script>'
                )

                return (
                    '<h2>Step 8: Test Record Checklist &amp; Hasil Uji (DAVITS)</h2>'
                    '<p class="wizard-help">Lengkapi checklist persiapan dan hasil pengujian untuk peralatan Davit. Data ini akan mencetak secara terpisah ke halaman 10 dan 11 pada PDF.</p>'
                    '<form method="post" action="/tptr/cover-wizard/step8/save" class="wizard-form">'
                    '<input type="hidden" name="csrf_token" value="{csrf}" />'
                    '<input type="hidden" name="project_id" value="{project_id}" />'
                    
                    '<h3 style="margin-top:24px;">4. Persiapan Sebelum Pengujian</h3>'
                    f'{prep_table}'
                    
                    '<h3 style="margin-top:28px;">5. Hasil Pengujian Davits (a &amp; b)</h3>'
                    f'{test_table}'
                    
                    '<h3 style="margin-top:28px;">5. c. Pengujian Waktu Pengangkatan &amp; Penurunan</h3>'
                    f'{hoisting_table_html}'
                    
                    '<h3 style="margin-top:28px;">5. d. Pengetesan Peralatan Keselamatan</h3>'
                    f'{safe_table}'
                    
                    '<h3 style="margin-top:28px;">Elemen di Panel Operasi (Alarm &amp; Indikator)</h3>'
                    f'{panel_table}'
                    
                    '__CATATAN_SECTION__'
                    
                    '<div class="wizard-actions" style="margin-top:32px;">'
                    '<button type="submit" class="wizard-btn wizard-btn-primary">Simpan &amp; Lanjut Step 9</button>'
                    '</div>'
                    '</form>'
                ).format(
                    csrf=html.escape(csrf_token, quote=True),
                    project_id=project.id,
                ).replace('__CATATAN_SECTION__', catatan_section_html)

            # RHIB template checklist form rendering
            if not form_data:
                form_data = {}
            
            # Setup defaults for all 22 items
            items_def = [
                ("prep_rhib_item1", 
                 "INSPEKTUR QUALITY ASSURANCE PT PAL MELAPORKAN KESIAPAN DARI RIGID HULL INFLATABLE BOAT (RHIB) & DAVITS.",
                 "Quality assurance inspector of PT PAL reports on the readiness of the Rigid Hull Inflatable Boat (RHIB) & Davits."),
                ("prep_rhib_item2",
                 "KEHADIRAN TIM PENGUJIAN.",
                 "Attendance of test team."),
                ("prep_rhib_item3",
                 "DOKUMEN PENDUKUNG SESUAI ITEM NO. 3 PADA TEST PROCEDURE TELAH TERSEDIA.",
                 "Document for the test according to item no. 3 in the test procedure are available."),
                ("prep_rhib_item4",
                 "PERALATAN YANG DIGUNAKAN SESUAI ITEM NO. 3 PADA TEST RECORD TELAH TERSEDIA.",
                 "Equipment to be used according to item no. 3 in the test record are available."),
                ("prep_rhib_item5",
                 "DOKUMEN HASIL PEMERIKSAAN PENGUJIAN (HPP) UNTUK RIGID HULL INFLATABLE BOAT (RHIB) & DAVITS.",
                 "Equipment testing results documents for Rigid Hull Inflatable Boat (RHIB) & Davits."),
                ("prep_rhib_item6",
                 "PERIKSA KONDISI RESCUE RHIB DAN PERALATAN NAVIGASI.",
                 "Check condition of Rescue RHIB with the navigation equipment."),
                ("prep_rhib_item7",
                 "PERIKSA APAKAH BAHAN BAKAR MESIN UTAMA SUDAH TERISI PENUH.",
                 "Check the condition outboard main engine fuel is fully charged."),
                ("prep_rhib_item8",
                 "PERIKSA APAKAH OLI HIDROLIK SISTEM KEMUDI SUDAH TERISI PENUH.",
                 "Check the condition of hydraulic oil steering system is full charged."),
                ("prep_rhib_item9",
                 "MENIMBANG RESCUE RHIB SEBELUM UJI COBA LAUT. BERAT RESCUE RHIB HARUS DALAM KONDISI BEBAN PENUH.",
                 "Considering the Rescue RHIB before sea trial. Weight the Rescue RHIB should be in full load condition."),
                ("prep_rhib_item10", "PERALATAN KESELAMATAN.", "Safety equipment."),
                ("prep_rhib_item11", "BAJU PENOLONG.", "Life jacket."),
                ("prep_rhib_item12", "TANGGA BONGKAR PASANG.", "Portable ladder."),
                ("prep_rhib_item13", "PERALATAN TALI TAMBAT.", "Mooring rope."),
                ("prep_rhib_item14", "DAMPRA.", "Fender."),
                ("prep_rhib_item15", "DAYUNG.", "Paddle."),
                ("prep_rhib_item16", "PEMADAM API JINJING.", "Portable fire extinguisher."),
                ("prep_rhib_item17", "PROSEDUR KESELAMATAN.", "Check for continuity of the wires."),
                ("prep_rhib_item18",
                 "MEMERIKSA URUTAN PEMASANGAN KABEL DARI SISTEM ELEKTRONIK.",
                 "Inspecting the cable installation sequence of the electronic system."),
                ("prep_rhib_item19",
                 "PERALATAN TALI TAMBAT DIGUNAKAN PADA SAAT KAPAL AKAN DAN SAAT SANDAR, DIIKATKAN PADA BORDER DERMAGA.",
                 "The mooring equipment is used when the ship will and when it is docked, tied to the dock border."),
                ("prep_rhib_item20",
                 "UNTUK TURUN KE KAPAL DAN NAIK DARI KAPAL KE DERMAGA, GUNAKAN TANGGA BONGKAR PASANG.",
                 "To get off the ship and ride from the ship to the dock, use the portable ladder."),
                ("prep_rhib_item21",
                 "APABILA TERJADI KEBAKARAN, SEGERA PADAMKAN DENGAN MENGGUNAKAN PEMADAM API JINJING.",
                 "In case of a fire, immediately turn off using a portable fire extinguisher."),
                ("prep_rhib_item22",
                 "APABILA MESIN PENGGERAK MATI, GUNAKAN DAYUNG UNTUK MENUJU KE DERMAGA TERDEKAT DAN ALAT BANTU RADIO KOMUNIKASI UNTUK MEMINTA BANTUAN.",
                 "When the drive engine is off, use the paddle to get to the nearest dock and radio communication aids to ask for help.")
            ]

            rows_html = []
            for i, (field_name, text_id, text_en) in enumerate(items_def):
                val = form_data.get(field_name) or getattr(project, field_name) or "ok"
                ok_checked = ' checked' if val == 'ok' else ''
                not_checked = ' checked' if val == 'not_ok' else ''
                
                rows_html.append(
                    f'<tr>'
                    f'<td style="padding:12px; border:1px solid #b7c9df;">'
                    f'<strong style="color: #1d4c90;">{i+1}. {html.escape(text_id)}</strong><br/>'
                    f'<small style="color:#557092; font-style:italic;">{html.escape(text_en)}</small>'
                    f'</td>'
                    f'<td style="padding:12px; border:1px solid #b7c9df; text-align:center; vertical-align:middle;">'
                    f'<input type="radio" name="{field_name}" value="ok"{ok_checked} required style="transform: scale(1.2); cursor: pointer;" />'
                    f'</td>'
                    f'<td style="padding:12px; border:1px solid #b7c9df; text-align:center; vertical-align:middle;">'
                    f'<input type="radio" name="{field_name}" value="not_ok"{not_checked} style="transform: scale(1.2); cursor: pointer;" />'
                    f'</td>'
                    f'</tr>'
                )

            table_content = "".join(rows_html)

            return (
                '<h2>Step 8: Test Record Checklist (RHIB)</h2>'
                '<p class="wizard-help">Lengkapi checklist kesiapan dan prosedur pengujian untuk Rigid Hull Inflatable Boat (RHIB). Data ini akan mengisi halaman 12 sampai 14 pada dokumen cetak.</p>'
                '<form method="post" action="/tptr/cover-wizard/step8/save" class="wizard-form">'
                '<input type="hidden" name="csrf_token" value="{csrf}" />'
                '<input type="hidden" name="project_id" value="{project_id}" />'
                '<table class="wizard-template-table" style="width:100%; border-collapse:collapse; border:1px solid #b7c9df; font-size:14px; margin-top:12px; background: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">'
                '<thead>'
                '<tr style="background:#1d4c90; color:#ffffff; font-size: 15px;">'
                '<th style="padding:12px; border:1px solid #b7c9df; text-align:left;">Item Pemeriksaan / Prosedur</th>'
                '<th style="padding:12px; border:1px solid #b7c9df; width:90px; text-align:center;">OK</th>'
                '<th style="padding:12px; border:1px solid #b7c9df; width:90px; text-align:center;">NOT OK</th>'
                '</tr>'
                '</thead>'
                '<tbody>'
                f'{table_content}'
                '</tbody>'
                '</table>'
                '<div class="wizard-actions" style="margin-top:24px;">'
                '<button type="submit" class="wizard-btn wizard-btn-primary">Simpan &amp; Lanjut Step 9</button>'
                '</div>'
                '</form>'
            ).format(
                csrf=html.escape(csrf_token, quote=True),
                project_id=project.id,
            )

        status_internal = form_data.get("status_review_internal") or "tidak"
        status_class_owner = form_data.get("status_review_class_owner_delegate") or "tidak"
        shipyard_checked = " checked" if form_data.get("tanda_tangan_shipyard") else ""
        class_checked = " checked" if form_data.get("tanda_tangan_class") else ""
        owner_checked = " checked" if form_data.get("tanda_tangan_owner_delegate") else ""

        return (
            '<h2>Step 9: Review &amp; Persetujuan</h2>'
            '<p class="wizard-help">Lengkapi status review dan tanda tangan persetujuan cover TPTR.</p>'
            '<form method="post" action="/tptr/cover-wizard/step9/save" class="wizard-form">'
            '<input type="hidden" name="csrf_token" value="{csrf}" />'
            '<input type="hidden" name="project_id" value="{project_id}" />'
            '<div class="wizard-grid">'
            '<label><span>Status Review Internal</span><select name="status_review_internal">'
            '<option value="ya"{ri_ya}>Ya</option>'
            '<option value="tidak"{ri_tidak}>Tidak</option>'
            "</select></label>"
            '<label><span>Status Review Class/Owner Delegate</span><select name="status_review_class_owner_delegate">'
            '<option value="ya"{ro_ya}>Ya</option>'
            '<option value="tidak"{ro_tidak}>Tidak</option>'
            "</select></label>"
            '<label class="wizard-checkbox"><input type="checkbox" name="tanda_tangan_shipyard"{shipyard_checked} /><span>Tanda Tangan Shipyard</span></label>'
            '<label class="wizard-checkbox"><input type="checkbox" name="tanda_tangan_class"{class_checked} /><span>Tanda Tangan Class</span></label>'
            '<label class="wizard-checkbox"><input type="checkbox" name="tanda_tangan_owner_delegate"{owner_checked} /><span>Tanda Tangan Owner Delegate</span></label>'
            "</div>"
            '<div class="wizard-actions"><button type="submit" class="wizard-btn wizard-btn-primary">Simpan Final</button></div>'
            "</form>"
        ).format(
            csrf=html.escape(csrf_token, quote=True),
            project_id=project.id,
            ri_ya=' selected="selected"' if status_internal == "ya" else "",
            ri_tidak=' selected="selected"' if status_internal == "tidak" else "",
            ro_ya=' selected="selected"' if status_class_owner == "ya" else "",
            ro_tidak=' selected="selected"' if status_class_owner == "tidak" else "",
            shipyard_checked=shipyard_checked,
            class_checked=class_checked,
            owner_checked=owner_checked,
        )

    # Tombol aksi akhir setelah semua step selesai.
    def _build_cover_wizard_final_actions(self, step: int, status: Optional[str], project: Any) -> str:
        if step != 9 or status != "completed" or not project:
            return ""
        return (
            '<section class="wizard-final">'
            '<h3>Pengisian selesai</h3>'
            "<p>Data cover dan body TPTR sudah lengkap. Lanjutkan ke halaman Jasper untuk unduh PDF.</p>"
            '<div class="wizard-actions">'
            '<a class="wizard-btn wizard-btn-primary" href="/tptr/jasper-cover?project_id={project_id}">Buka Jasper Cover</a>'
            '<a class="wizard-btn wizard-btn-soft" href="/tptr/cover-wizard?step=1">Mulai Project Baru</a>'
            "</div>"
            "</section>"
        ).format(project_id=project.id)

    # Render halaman wizard cover TPTR dari template HTML statis.
    def _render_cover_wizard_page(
        self,
        step: int,
        project: Any = None,
        status: Optional[str] = None,
        error_message: Optional[str] = None,
        warning_message: Optional[str] = None,
        form_data: Optional[Mapping[str, Any]] = None,
        selected_template_tptr: Optional[str] = None,
    ) -> str:
        template_html = self._load_cover_wizard_template()
        csrf_token = request.csrf_token()

        if step == 0:
            main_content = self._build_cover_wizard_hub_view()
        else:
            main_content = (
                '<section class="wizard-resume">'
                '<h2>Pilih atau Ganti Project Aktif</h2>'
                '<p class="wizard-help">Gunakan daftar ini jika Anda ingin melanjutkan project lain tanpa kembali ke hub.</p>'
                '<form action="/tptr/cover-wizard" method="get" class="wizard-resume-form">'
                f'<input type="hidden" name="step" value="{step}" />'
                '<select name="project_id">'
                f'{self._build_cover_wizard_resume_options(project)}'
                '</select>'
                '<button type="submit" class="wizard-btn wizard-btn-soft">Buka Project</button>'
                '</form>'
                '</section>'
                '<section class="wizard-stepper-wrap">'
                f'{self._build_cover_wizard_stepper(step, project)}'
                '</section>'
                f'{self._build_cover_wizard_project_summary(project, step)}'
                '<section class="wizard-form-card">'
                f'{self._build_cover_wizard_step_form(step, project, csrf_token, form_data=form_data, selected_template_tptr=selected_template_tptr)}'
                '</section>'
                f'{self._build_cover_wizard_final_actions(step, status, project)}'
            )

        replacements = {
            "__STATUS_BLOCK__": self._build_cover_wizard_status_block(
                status=status,
                error_message=error_message,
                warning_message=warning_message,
            ),
            "__PAGE_INTRO__": self._build_cover_wizard_page_intro(step, project),
            "__MAIN_CONTENT__": main_content,
        }

        rendered_html = template_html
        for placeholder, value in replacements.items():
            rendered_html = rendered_html.replace(placeholder, value)
        return rendered_html

    # Helper ini membaca template HTML statis untuk halaman download Jasper (tanpa request.render QWeb).
    def _load_jasper_html_template(self) -> str:
        template_path = get_module_resource(
            "data_kapal",
            "static",
            "src",
            "html",
            "jasper_cover_page.html",
        )
        if not template_path:
            raise UserError("Template HTML Jasper tidak ditemukan di modul data_kapal.")

        try:
            with open(template_path, "r", encoding="utf-8") as template_file:
                return template_file.read()
        except OSError as exc:
            raise UserError("Gagal membaca template HTML Jasper: %s" % exc)

    # Data preview ini ditampilkan di panel informasi agar user tahu data proyek yang akan dicetak.
    def _get_jasper_preview_data(self, project: Any) -> Dict[str, str]:
        if not project:
            return {
                "project_name": "-",
                "project_no": "-",
                "owner": "-",
                "class_name": "-",
                "drawing_document_name": "-",
                "scale": "-",
            }

        cover_data = project._get_cover_sheet_data()
        return {
            "project_name": project.nama_kapal or "-",
            "project_no": project.nomor_proyek or "-",
            "owner": project.delegasi_pemilik or "-",
            "class_name": project.kelas_kapal or "-",
            "drawing_document_name": cover_data.get("drawing_document_name") or "-",
            "scale": cover_data.get("scale") or "-",
        }

    # Banner status dipakai untuk menampilkan feedback validasi atau error Jasper di halaman HTML.
    def _build_jasper_status_block(self, status: Optional[str], error_message: Optional[str] = None) -> str:
        if status == "invalid_project":
            return '<div class="alert alert-warning">Proyek tidak valid atau belum dipilih.</div>'
        if status == "download_error":
            safe_message = html.escape(error_message or "Terjadi error saat mengunduh PDF.", quote=True)
            return '<div class="alert alert-danger">Gagal membuat PDF Jasper: %s</div>' % safe_message
        return ""

    # Render manual via string replacement agar halaman web tetap HTML/CSS biasa (tanpa render engine QWeb).
    def _render_jasper_cover_page(
        self,
        projects: Any,
        selected_project: Any,
        status: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> str:
        template_html = self._load_jasper_html_template()
        selected_preview = self._get_jasper_preview_data(selected_project)
        status_block = self._build_jasper_status_block(status=status, error_message=error_message)

        options = ['<option value="">Pilih proyek...</option>']
        for project in projects:
            preview = self._get_jasper_preview_data(project)
            option_label = "%s - %s" % (project.nomor_proyek or "-", project.nama_kapal or "Tanpa Nama")
            selected_attr = ""
            if selected_project and project.id == selected_project.id:
                selected_attr = ' selected="selected"'

            options.append(
                (
                    '<option value="{id}" data-project-name="{project_name}" data-project-no="{project_no}" '
                    'data-owner="{owner}" data-class-name="{class_name}" '
                    'data-drawing-document-name="{drawing_document_name}" data-scale="{scale}"{selected}>{label}</option>'
                ).format(
                    id=project.id,
                    project_name=html.escape(preview["project_name"], quote=True),
                    project_no=html.escape(preview["project_no"], quote=True),
                    owner=html.escape(preview["owner"], quote=True),
                    class_name=html.escape(preview["class_name"], quote=True),
                    drawing_document_name=html.escape(preview["drawing_document_name"], quote=True),
                    scale=html.escape(preview["scale"], quote=True),
                    selected=selected_attr,
                    label=html.escape(option_label, quote=True),
                )
            )

        replacements = {
            "__STATUS_BLOCK__": status_block,
            "__CSRF_TOKEN__": request.csrf_token(),
            "__PROJECT_OPTIONS__": "\n".join(options),
            "__PROJECT_NAME__": html.escape(selected_preview["project_name"], quote=True),
            "__PROJECT_NO__": html.escape(selected_preview["project_no"], quote=True),
            "__OWNER__": html.escape(selected_preview["owner"], quote=True),
            "__CLASS_NAME__": html.escape(selected_preview["class_name"], quote=True),
            "__DRAWING_DOCUMENT_NAME__": html.escape(selected_preview["drawing_document_name"], quote=True),
            "__SCALE__": html.escape(selected_preview["scale"], quote=True),
        }

        rendered_html = template_html
        for placeholder, value in replacements.items():
            rendered_html = rendered_html.replace(placeholder, value)
        return rendered_html

    # Helper ini membaca template HTML statis untuk halaman review & persetujuan terpisah.
    def _load_review_persetujuan_html_template(self) -> str:
        template_path = get_module_resource(
            "data_kapal",
            "static",
            "src",
            "html",
            "review_persetujuan_page.html",
        )
        if not template_path:
            raise UserError("Template HTML Review & Persetujuan tidak ditemukan di modul data_kapal.")

        try:
            with open(template_path, "r", encoding="utf-8") as template_file:
                return template_file.read()
        except OSError as exc:
            raise UserError("Gagal membaca template HTML Review & Persetujuan: %s" % exc)

    # Ambil default isi form review dari data terakhir proyek agar user tidak mengisi dari nol.
    def _get_review_form_defaults(self, project: Any) -> Dict[str, Any]:
        defaults: Dict[str, Any] = {
            "status_review_internal": "tidak",
            "status_review_class_owner_delegate": "tidak",
            "tanda_tangan_shipyard": False,
            "tanda_tangan_class": False,
            "tanda_tangan_owner_delegate": False,
            "drawn_by_name": "",
            "designed_by_name": "",
            "checked_by_name": "",
            "approved_by_name": "",
            "tanggal_drawn_by": "",
            "tanggal_designed_by": "",
            "tanggal_checked_by": "",
            "tanggal_approved_by": "",
        }
        if not project:
            return defaults

        latest_review = request.env["tptr.review_persetujuan"].search(
            [("tp_id", "=", project.id)],
            order="tanggal_input desc, id desc",
            limit=1,
        )
        if not latest_review:
            return defaults

        defaults.update(
            {
                "status_review_internal": latest_review.status_review_internal or "tidak",
                "status_review_class_owner_delegate": latest_review.status_review_class_owner_delegate or "tidak",
                "tanda_tangan_shipyard": bool(latest_review.tanda_tangan_shipyard),
                "tanda_tangan_class": bool(latest_review.tanda_tangan_class),
                "tanda_tangan_owner_delegate": bool(latest_review.tanda_tangan_owner_delegate),
                "drawn_by_name": latest_review.drawn_by_name or "",
                "designed_by_name": latest_review.designed_by_name or "",
                "checked_by_name": latest_review.checked_by_name or "",
                "approved_by_name": latest_review.approved_by_name or "",
                "tanggal_drawn_by": str(latest_review.tanggal_drawn_by or ""),
                "tanggal_designed_by": str(latest_review.tanggal_designed_by or ""),
                "tanggal_checked_by": str(latest_review.tanggal_checked_by or ""),
                "tanggal_approved_by": str(latest_review.tanggal_approved_by or ""),
            }
        )
        return defaults

    # Banner status untuk feedback simpan review atau error validasi.
    def _build_review_status_block(self, status: Optional[str], error_message: Optional[str] = None) -> str:
        if error_message:
            safe_message = html.escape(error_message, quote=True)
            return '<div class="alert alert-danger">%s</div>' % safe_message

        status_map = {
            "saved": ("success", "Data review & persetujuan berhasil disimpan."),
            "invalid_project": ("warning", "Project tidak valid atau belum dipilih."),
            "preview_error": ("warning", "Preview gagal dimuat. Cek konfigurasi Jasper Server."),
        }
        css_name, message = status_map.get(status, (None, None))
        if not css_name or not message:
            return ""
        return '<div class="alert alert-%s">%s</div>' % (css_name, message)

    # Render halaman review terpisah: preview dokumen + form review yang tersimpan ke model review.
    def _render_review_persetujuan_page(
        self,
        projects: Any,
        selected_project: Any,
        status: Optional[str] = None,
        error_message: Optional[str] = None,
        form_data: Optional[Mapping[str, Any]] = None,
    ) -> str:
        template_html = self._load_review_persetujuan_html_template()
        status_block = self._build_review_status_block(status=status, error_message=error_message)
        preview_data = self._get_jasper_preview_data(selected_project)

        form_values = self._get_review_form_defaults(selected_project)
        if form_data:
            form_values.update(dict(form_data))

        selected_status_internal = (form_values.get("status_review_internal") or "tidak").strip()
        selected_status_class_owner = (form_values.get("status_review_class_owner_delegate") or "tidak").strip()

        options = ['<option value="">Pilih proyek...</option>']
        for project in projects:
            option_label = "%s - %s" % (project.nomor_proyek or "-", project.nama_kapal or "Tanpa Nama")
            selected_attr = ""
            if selected_project and project.id == selected_project.id:
                selected_attr = ' selected="selected"'
            options.append(
                '<option value="{id}"{selected}>{label}</option>'.format(
                    id=project.id,
                    selected=selected_attr,
                    label=html.escape(option_label, quote=True),
                )
            )

        project_id_value = str(selected_project.id) if selected_project else ""
        preview_url = (
            "/tptr/review-persetujuan/preview?project_id=%s" % selected_project.id
            if selected_project
            else ""
        )

        replacements = {
            "__STATUS_BLOCK__": status_block,
            "__CSRF_TOKEN__": request.csrf_token(),
            "__PROJECT_OPTIONS__": "\n".join(options),
            "__PROJECT_ID__": html.escape(project_id_value, quote=True),
            "__PREVIEW_URL__": html.escape(preview_url, quote=True),
            "__PROJECT_NAME__": html.escape(preview_data["project_name"], quote=True),
            "__PROJECT_NO__": html.escape(preview_data["project_no"], quote=True),
            "__OWNER__": html.escape(preview_data["owner"], quote=True),
            "__CLASS_NAME__": html.escape(preview_data["class_name"], quote=True),
            "__DRAWING_DOCUMENT_NAME__": html.escape(preview_data["drawing_document_name"], quote=True),
            "__RI_YA_SELECTED__": ' selected="selected"' if selected_status_internal == "ya" else "",
            "__RI_TIDAK_SELECTED__": ' selected="selected"' if selected_status_internal != "ya" else "",
            "__RO_YA_SELECTED__": ' selected="selected"' if selected_status_class_owner == "ya" else "",
            "__RO_TIDAK_SELECTED__": ' selected="selected"' if selected_status_class_owner != "ya" else "",
            "__TTD_SHIPYARD_CHECKED__": ' checked="checked"' if form_values.get("tanda_tangan_shipyard") else "",
            "__TTD_CLASS_CHECKED__": ' checked="checked"' if form_values.get("tanda_tangan_class") else "",
            "__TTD_OWNER_CHECKED__": ' checked="checked"' if form_values.get("tanda_tangan_owner_delegate") else "",
            "__DRAWN_BY_NAME__": html.escape(form_values.get("drawn_by_name") or "", quote=True),
            "__DESIGNED_BY_NAME__": html.escape(form_values.get("designed_by_name") or "", quote=True),
            "__CHECKED_BY_NAME__": html.escape(form_values.get("checked_by_name") or "", quote=True),
            "__APPROVED_BY_NAME__": html.escape(form_values.get("approved_by_name") or "", quote=True),
            "__TANGGAL_DRAWN_BY__": html.escape(form_values.get("tanggal_drawn_by") or "", quote=True),
            "__TANGGAL_DESIGNED_BY__": html.escape(form_values.get("tanggal_designed_by") or "", quote=True),
            "__TANGGAL_CHECKED_BY__": html.escape(form_values.get("tanggal_checked_by") or "", quote=True),
            "__TANGGAL_APPROVED_BY__": html.escape(form_values.get("tanggal_approved_by") or "", quote=True),
        }

        rendered_html = template_html
        for placeholder, value in replacements.items():
            rendered_html = rendered_html.replace(placeholder, value)
        return rendered_html

    @http.route("/tptr/kapal-proyek", type="http", auth="user", website=True, methods=["GET"])
    def kapal_proyek_page(self, **kwargs):
        record = None
        edit_id = kwargs.get("edit_id")
        if edit_id and str(edit_id).isdigit():
            record = request.env["pal.kapal.proyek"].browse(int(edit_id)).exists()
        status = kwargs.get("status")
        page_html = self._render_kapal_proyek_page(record=record, status=status)
        return request.make_response(
            page_html,
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )

    @http.route("/tptr/kapal-proyek/create", type="http", auth="user", website=True, methods=["POST"])
    def kapal_proyek_create(self, **post):
        payload = self._build_payload(post)
        error = self._validate_payload(payload)

        if error:
            page_html = self._render_kapal_proyek_page(form_data=payload, error=error)
            return request.make_response(
                page_html,
                headers=[("Content-Type", "text/html; charset=utf-8")],
            )

        request.env["pal.kapal.proyek"].create(payload)
        return request.redirect("/tptr/kapal-proyek?status=created")

    @http.route(
        "/tptr/kapal-proyek/<int:record_id>/update",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def kapal_proyek_update(self, record_id, **post):
        record = request.env["pal.kapal.proyek"].browse(record_id).exists()
        if not record:
            return request.redirect("/tptr/kapal-proyek?status=not_found")

        payload = self._build_payload(post)
        error = self._validate_payload(payload)

        if error:
            page_html = self._render_kapal_proyek_page(record=record, form_data=payload, error=error)
            return request.make_response(
                page_html,
                headers=[("Content-Type", "text/html; charset=utf-8")],
            )

        record.write(payload)
        return request.redirect("/tptr/kapal-proyek?status=updated")

    @http.route(
        "/tptr/kapal-proyek/<int:record_id>/delete",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def kapal_proyek_delete(self, record_id, **post):
        record = request.env["pal.kapal.proyek"].browse(record_id).exists()
        if record:
            record.unlink()
            return request.redirect("/tptr/kapal-proyek?status=deleted")
        return request.redirect("/tptr/kapal-proyek?status=not_found")

    # Wizard step-by-step untuk pengisian cover TPTR.
    @http.route("/tptr/cover-wizard", type="http", auth="user", website=True, methods=["GET"])
    def tptr_cover_wizard_page(self, **kwargs):
        step_raw = (kwargs.get("step") or "0").strip()
        step = int(step_raw) if step_raw.isdigit() and 0 <= int(step_raw) <= 9 else 0
        project = self._get_project_from_id(kwargs.get("project_id"))
        selected_template_tptr = (kwargs.get("template_tptr") or "").strip()

        guarded_step, warning_message = self._guard_wizard_step(step, project)
        step = guarded_step

        page_html = self._render_cover_wizard_page(
            step=step,
            project=project,
            status=kwargs.get("status"),
            error_message=kwargs.get("error"),
            warning_message=warning_message,
            selected_template_tptr=selected_template_tptr,
        )
        return request.make_response(
            page_html,
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )

    # Simpan Step 1 (Data Kapal & Proyek), lalu redirect ke Step 2.
    @http.route("/tptr/cover-wizard/step1/save", type="http", auth="user", website=True, methods=["POST"], csrf=True)
    def tptr_cover_wizard_step1_save(self, **post):
        payload = self._build_payload(post)
        validation_error = self._validate_payload(payload)
        project = self._get_project_from_id(post.get("project_id"))

        if validation_error:
            form_data = dict(payload)
            if project:
                form_data["project_id"] = project.id
            page_html = self._render_cover_wizard_page(
                step=1,
                project=project,
                error_message=validation_error,
                form_data=form_data,
            )
            return request.make_response(
                page_html,
                headers=[("Content-Type", "text/html; charset=utf-8")],
            )

        if project:
            project.write(payload)
        else:
            project = request.env["pal.kapal.proyek"].create(payload)

        # Upload simbol proyek opsional dari QA untuk dipakai di area PROJECT SYMBOL pada cover.
        symbol_file = request.httprequest.files.get("project_symbol")
        if symbol_file and symbol_file.filename:
            symbol_bytes = symbol_file.read()
            if symbol_bytes:
                project.write({"project_symbol": base64.b64encode(symbol_bytes)})

        return request.redirect("/tptr/cover-wizard?step=2&project_id=%s&status=step1_saved" % project.id)

    # Simpan Step 2 (Lokasi & Kelas Pengujian), lalu redirect ke Step 3.
    @http.route("/tptr/cover-wizard/step2/save", type="http", auth="user", website=True, methods=["POST"], csrf=True)
    def tptr_cover_wizard_step2_save(self, **post):
        project = self._get_project_from_id(post.get("project_id"))
        if not project:
            return request.redirect("/tptr/cover-wizard?step=1&status=invalid_project")

        latest_lokasi = request.env["tptr.lokasi_kelas"].search(
            [("kapal_id", "=", project.id)],
            order="tanggal_input desc, id desc",
            limit=1,
        )
        lokasi_pengujian = (post.get("lokasi_pengujian") or "").strip()
        note = (post.get("note") or "").strip()
        sign_class = bool(post.get("sign_class"))
        sign_signature_file = request.httprequest.files.get("sign_class_signature")
        sign_signature_bytes = b""
        sign_signature_filename = ""
        if sign_signature_file and sign_signature_file.filename:
            sign_signature_filename = (sign_signature_file.filename or "").strip()
            sign_signature_bytes = sign_signature_file.read() or b""

        if not lokasi_pengujian:
            page_html = self._render_cover_wizard_page(
                step=2,
                project=project,
                error_message="Lokasi Pengujian wajib diisi.",
                form_data={
                    "lokasi_pengujian": lokasi_pengujian,
                    "note": note,
                    "sign_class": sign_class,
                    "sign_class_signature_filename": sign_signature_filename,
                },
            )
            return request.make_response(
                page_html,
                headers=[("Content-Type", "text/html; charset=utf-8")],
            )

        # Jika Sign Class dicentang, upload tanda tangan menjadi wajib.
        existing_sign_signature = latest_lokasi.sign_class_signature if latest_lokasi and latest_lokasi.sign_class_signature else False
        existing_sign_filename = (
            latest_lokasi.sign_class_signature_filename if latest_lokasi and latest_lokasi.sign_class_signature_filename else ""
        )
        if sign_class and not sign_signature_bytes and not existing_sign_signature:
            page_html = self._render_cover_wizard_page(
                step=2,
                project=project,
                error_message="Upload tanda tangan Class wajib saat Sign Class dicentang.",
                form_data={
                    "lokasi_pengujian": lokasi_pengujian,
                    "note": note,
                    "sign_class": sign_class,
                    "sign_class_signature_filename": sign_signature_filename,
                },
            )
            return request.make_response(
                page_html,
                headers=[("Content-Type", "text/html; charset=utf-8")],
            )

        lokasi_vals = {
            "kapal_id": project.id,
            "lokasi_pengujian": lokasi_pengujian,
            "sign_class": sign_class,
            "note": note,
        }
        if sign_class and sign_signature_bytes:
            lokasi_vals.update(
                {
                    "sign_class_signature": base64.b64encode(sign_signature_bytes),
                    "sign_class_signature_filename": sign_signature_filename or "sign_class_signature.png",
                }
            )
        elif sign_class and existing_sign_signature:
            lokasi_vals.update(
                {
                    "sign_class_signature": existing_sign_signature,
                    "sign_class_signature_filename": existing_sign_filename or "sign_class_signature.png",
                }
            )

        request.env["tptr.lokasi_kelas"].create(lokasi_vals)
        return request.redirect("/tptr/cover-wizard?step=3&project_id=%s&status=step2_saved" % project.id)

    # Simpan Step 3 (Dokumen Pendukung), lalu redirect ke Step 4.
    @http.route("/tptr/cover-wizard/step3/save", type="http", auth="user", website=True, methods=["POST"], csrf=True)
    def tptr_cover_wizard_step3_save(self, **post):
        project = self._get_project_from_id(post.get("project_id"))
        if not project:
            return request.redirect("/tptr/cover-wizard?step=1&status=invalid_project")

        referensi_desain = (post.get("referensi_desain") or "").strip()
        dokumen_maker = (post.get("dokumen_maker") or "").strip()
        keterangan = (post.get("keterangan") or "").strip()

        if not referensi_desain or not dokumen_maker:
            page_html = self._render_cover_wizard_page(
                step=3,
                project=project,
                error_message="Referensi Desain dan Dokumen Maker wajib diisi.",
                form_data={
                    "referensi_desain": referensi_desain,
                    "dokumen_maker": dokumen_maker,
                    "keterangan": keterangan,
                },
            )
            return request.make_response(
                page_html,
                headers=[("Content-Type", "text/html; charset=utf-8")],
            )

        request.env["tptr.dokumen_pendukung"].create(
            {
                "tp_id": project.id,
                "referensi_desain": referensi_desain,
                "dokumen_maker": dokumen_maker,
                "keterangan": keterangan,
            }
        )
        return request.redirect("/tptr/cover-wizard?step=4&project_id=%s&status=step3_saved" % project.id)

    # Simpan Step 4 (Body TPTR halaman 5), lalu redirect ke Step 5.
    @http.route("/tptr/cover-wizard/step4/save", type="http", auth="user", website=True, methods=["POST"], csrf=True)
    def tptr_cover_wizard_step4_save(self, **post):
        project = self._get_project_from_id(post.get("project_id"))
        if not project:
            return request.redirect("/tptr/cover-wizard?step=1&status=invalid_project")

        body_test_related_project_no = (post.get("body_test_related_project_no") or "").strip()
        body_contract_specification = (post.get("body_contract_specification") or "").strip()
        body_delegate_name = (post.get("body_delegate_name") or "").strip()
        body_pt_pal_name = (post.get("body_pt_pal_name") or "").strip()
        delegate_signature_bytes, delegate_signature_filename = self._extract_signature_input(
            "body_delegate_signature_file",
            "body_delegate_signature_drawn",
            "delegate_signature.png",
        )
        pt_pal_signature_bytes, pt_pal_signature_filename = self._extract_signature_input(
            "body_pt_pal_signature_file",
            "body_pt_pal_signature_drawn",
            "pt_pal_signature.png",
        )

        if not body_test_related_project_no or not body_contract_specification:
            page_html = self._render_cover_wizard_page(
                step=4,
                project=project,
                error_message="Pengujian untuk Nomor Proyek dan Spesifikasi Kontrak wajib diisi.",
                form_data={
                    "body_test_related_project_no": body_test_related_project_no,
                    "body_contract_specification": body_contract_specification,
                    "body_delegate_name": body_delegate_name,
                    "body_pt_pal_name": body_pt_pal_name,
                    "body_delegate_signature_filename": delegate_signature_filename or project.body_delegate_signature_filename or "",
                    "body_pt_pal_signature_filename": pt_pal_signature_filename or project.body_pt_pal_signature_filename or "",
                    "body_delegate_signature_date": str(project.body_delegate_signature_date or ""),
                    "body_pt_pal_signature_date": str(project.body_pt_pal_signature_date or ""),
                },
            )
            return request.make_response(
                page_html,
                headers=[("Content-Type", "text/html; charset=utf-8")],
            )

        write_vals = {
            "body_test_related_project_no": body_test_related_project_no,
            "body_contract_specification": body_contract_specification,
            "body_delegate_name": body_delegate_name or project.delegasi_pemilik or "",
            "body_pt_pal_name": body_pt_pal_name,
        }
        today = fields.Date.context_today(project)
        if delegate_signature_bytes:
            write_vals.update(
                {
                    "body_delegate_signature": base64.b64encode(delegate_signature_bytes),
                    "body_delegate_signature_filename": delegate_signature_filename or "delegate_signature.png",
                    "body_delegate_signature_date": today,
                }
            )
        if pt_pal_signature_bytes:
            write_vals.update(
                {
                    "body_pt_pal_signature": base64.b64encode(pt_pal_signature_bytes),
                    "body_pt_pal_signature_filename": pt_pal_signature_filename or "pt_pal_signature.png",
                    "body_pt_pal_signature_date": today,
                }
            )

        project.write(write_vals)
        return request.redirect("/tptr/cover-wizard?step=5&project_id=%s&status=step4_saved" % project.id)

    # Simpan Step 5 (Body TPTR halaman 6), lalu redirect ke Step 6.
    @http.route("/tptr/cover-wizard/step5/save", type="http", auth="user", website=True, methods=["POST"], csrf=True)
    def tptr_cover_wizard_step5_save(self, **post):
        project = self._get_project_from_id(post.get("project_id"))
        if not project:
            return request.redirect("/tptr/cover-wizard?step=1&status=invalid_project")

        body_supporting_reference = (post.get("body_supporting_reference") or "").strip()
        body_condition = (post.get("body_condition") or "").strip()
        body_time = (post.get("body_time") or "").strip()

        if not body_supporting_reference or not body_condition or not body_time:
            page_html = self._render_cover_wizard_page(
                step=5,
                project=project,
                error_message="Referensi Pendukung, Kondisi, dan Waktu wajib diisi.",
                form_data={
                    "body_supporting_reference": body_supporting_reference,
                    "body_condition": body_condition,
                    "body_time": body_time,
                },
            )
            return request.make_response(
                page_html,
                headers=[("Content-Type", "text/html; charset=utf-8")],
            )

        project.write(
            {
                "body_supporting_reference": body_supporting_reference,
                "body_condition": body_condition,
                "body_time": body_time,
            }
        )
        return request.redirect("/tptr/cover-wizard?step=6&project_id=%s&status=step5_saved" % project.id)

    # Simpan Step 6 (Test Record Halaman 7), lalu redirect ke Step 7.
    @http.route("/tptr/cover-wizard/step6/save", type="http", auth="user", website=True, methods=["POST"], csrf=True)
    def tptr_cover_wizard_step6_save(self, **post):
        project = self._get_project_from_id(post.get("project_id"))
        if not project:
            return request.redirect("/tptr/cover-wizard?step=1&status=invalid_project")

        test_record_general_date = (post.get("test_record_general_date") or "").strip()
        test_record_general_place = (post.get("test_record_general_place") or "").strip()
        test_record_general_team_leader = (post.get("test_record_general_team_leader") or "").strip()
        test_record_general_delegate_name = (post.get("test_record_general_delegate_name") or "").strip()
        test_record_general_class_surveyor_name = (post.get("test_record_general_class_surveyor_name") or "").strip()

        member_list = []
        for i in range(1, 5):
            val = (post.get("test_record_general_member_%s" % i) or "").strip()
            if val:
                member_list.append(val)
        test_record_general_members = "\n".join(member_list)

        is_davits = (project.template_tptr == "davits_rhib")

        # Validation checks
        has_error = False
        if not test_record_general_date or not test_record_general_place or not test_record_general_team_leader or not test_record_general_members or not test_record_general_delegate_name:
            has_error = True
        if is_davits and not test_record_general_class_surveyor_name:
            has_error = True

        if has_error:
            page_html = self._render_cover_wizard_page(
                step=6,
                project=project,
                error_message="Semua kolom wajib diisi.",
                form_data={
                    "test_record_general_date": test_record_general_date,
                    "test_record_general_place": test_record_general_place,
                    "test_record_general_team_leader": test_record_general_team_leader,
                    "test_record_general_member_1": post.get("test_record_general_member_1") or "",
                    "test_record_general_member_2": post.get("test_record_general_member_2") or "",
                    "test_record_general_member_3": post.get("test_record_general_member_3") or "",
                    "test_record_general_member_4": post.get("test_record_general_member_4") or "",
                    "test_record_general_delegate_name": test_record_general_delegate_name,
                    "test_record_general_class_surveyor_name": test_record_general_class_surveyor_name,
                },
            )
            return request.make_response(
                page_html,
                headers=[("Content-Type", "text/html; charset=utf-8")],
            )

        project.write(
            {
                "test_record_general_date": fields.Date.from_string(test_record_general_date),
                "test_record_general_place": test_record_general_place,
                "test_record_general_team_leader": test_record_general_team_leader,
                "test_record_general_members": test_record_general_members,
                "test_record_general_delegate_name": test_record_general_delegate_name,
                "test_record_general_class_surveyor_name": test_record_general_class_surveyor_name,
            }
        )
        return request.redirect("/tptr/cover-wizard?step=7&project_id=%s&status=step6_saved" % project.id)

    # Simpan Step 7 (Test Record Spesifikasi), lalu redirect ke Step 8.
    @http.route("/tptr/cover-wizard/step7/save", type="http", auth="user", website=True, methods=["POST"], csrf=True)
    def tptr_cover_wizard_step7_save(self, **post):
        project = self._get_project_from_id(post.get("project_id"))
        if not project:
            return request.redirect("/tptr/cover-wizard?step=1&status=invalid_project")

        is_davits = (project.template_tptr == "davits_rhib")
        
        equip_names_id = request.httprequest.form.getlist("equip_name_id[]")
        equip_names_en = request.httprequest.form.getlist("equip_name_en[]")

        equip_names_id = [x.strip() for x in equip_names_id if x is not None]
        equip_names_en = [x.strip() for x in equip_names_en if x is not None]

        # Validation checks for equipment list
        valid_equipment = True
        if not equip_names_id or not equip_names_en or len(equip_names_id) != len(equip_names_en):
            valid_equipment = False
        else:
            for name_id, name_en in zip(equip_names_id, equip_names_en):
                if not name_id or not name_en:
                    valid_equipment = False
                    break

        if not valid_equipment:
            form_data = {**post}
            form_data["equip_name_id[]"] = equip_names_id
            form_data["equip_name_en[]"] = equip_names_en
            page_html = self._render_cover_wizard_page(
                step=7,
                project=project,
                error_message="Semua kolom peralatan wajib diisi.",
                form_data=form_data,
            )
            return request.make_response(
                page_html,
                headers=[("Content-Type", "text/html; charset=utf-8")],
            )

        write_vals = {}
        
        if is_davits:
            davit_maker = (post.get("davit_maker") or "").strip()
            davit_model = (post.get("davit_model") or "").strip()
            davit_type = (post.get("davit_type") or "").strip()
            davit_hoisting_speed = (post.get("davit_hoisting_speed") or "").strip()
            davit_lifting_height = (post.get("davit_lifting_height") or "").strip()
            davit_swl = (post.get("davit_swl") or "").strip()
            davit_number = (post.get("davit_number") or "").strip()

            if not davit_maker or not davit_model or not davit_type or not davit_hoisting_speed or not davit_lifting_height or not davit_swl or not davit_number:
                form_data = {**post}
                form_data["equip_name_id[]"] = equip_names_id
                form_data["equip_name_en[]"] = equip_names_en
                page_html = self._render_cover_wizard_page(
                    step=7,
                    project=project,
                    error_message="Semua kolom spesifikasi Davit wajib diisi.",
                    form_data=form_data,
                )
                return request.make_response(
                    page_html,
                    headers=[("Content-Type", "text/html; charset=utf-8")],
                )

            write_vals.update({
                "davit_maker": davit_maker,
                "davit_model": davit_model,
                "davit_type": davit_type,
                "davit_hoisting_speed": davit_hoisting_speed,
                "davit_lifting_height": davit_lifting_height,
                "davit_swl": davit_swl,
                "davit_number": davit_number,
            })
        else:
            rhib_maker = (post.get("rhib_maker") or "").strip()
            rhib_loa = (post.get("rhib_loa") or "").strip()
            rhib_hull_length = (post.get("rhib_hull_length") or "").strip()
            rhib_breadth = (post.get("rhib_breadth") or "").strip()
            rhib_hull_height = (post.get("rhib_hull_height") or "").strip()
            rhib_draft = (post.get("rhib_draft") or "").strip()
            rhib_engine = (post.get("rhib_engine") or "").strip()
            rhib_number = (post.get("rhib_number") or "").strip()
            rhib_max_speed = (post.get("rhib_max_speed") or "").strip()
            rhib_cruising_speed = (post.get("rhib_cruising_speed") or "").strip()
            rhib_capacity = (post.get("rhib_capacity") or "").strip()
            rhib_boat_weight = (post.get("rhib_boat_weight") or "").strip()
            rhib_total_weight = (post.get("rhib_total_weight") or "").strip()
            rhib_assumed_weight = (post.get("rhib_assumed_weight") or "").strip()
            rhib_unit_count = (post.get("rhib_unit_count") or "").strip()

            if not rhib_maker or not rhib_loa or not rhib_hull_length or not rhib_breadth or not rhib_hull_height or not rhib_draft or not rhib_engine or not rhib_number or not rhib_max_speed or not rhib_cruising_speed or not rhib_capacity or not rhib_boat_weight or not rhib_total_weight or not rhib_assumed_weight or not rhib_unit_count:
                form_data = {**post}
                form_data["equip_name_id[]"] = equip_names_id
                form_data["equip_name_en[]"] = equip_names_en
                page_html = self._render_cover_wizard_page(
                    step=7,
                    project=project,
                    error_message="Semua kolom spesifikasi RHIB wajib diisi.",
                    form_data=form_data,
                )
                return request.make_response(
                    page_html,
                    headers=[("Content-Type", "text/html; charset=utf-8")],
                )

            write_vals.update({
                "rhib_maker": rhib_maker,
                "rhib_loa": rhib_loa,
                "rhib_hull_length": rhib_hull_length,
                "rhib_breadth": rhib_breadth,
                "rhib_hull_height": rhib_hull_height,
                "rhib_draft": rhib_draft,
                "rhib_engine": rhib_engine,
                "rhib_number": rhib_number,
                "rhib_max_speed": rhib_max_speed,
                "rhib_cruising_speed": rhib_cruising_speed,
                "rhib_capacity": rhib_capacity,
                "rhib_boat_weight": rhib_boat_weight,
                "rhib_total_weight": rhib_total_weight,
                "rhib_assumed_weight": rhib_assumed_weight,
                "rhib_unit_count": rhib_unit_count,
            })

        # Save specifications
        project.write(write_vals)

        # Clear and rebuild the equipment list dynamically
        project.peralatan_ids.unlink()
        peralatan_vals = []
        for i, (name_id, name_en) in enumerate(zip(equip_names_id, equip_names_en)):
            peralatan_vals.append({
                "kapal_id": project.id,
                "name_id": name_id,
                "name_en": name_en,
                "sequence": (i + 1) * 10,
            })
        
        if peralatan_vals:
            request.env["tptr.peralatan"].create(peralatan_vals)

        return request.redirect("/tptr/cover-wizard?step=8&project_id=%s&status=step7_saved" % project.id)

    # Simpan Step 8 (Test Record Checklist), lalu redirect ke Step 9.
    @http.route("/tptr/cover-wizard/step8/save", type="http", auth="user", website=True, methods=["POST"], csrf=True)
    def tptr_cover_wizard_step8_save(self, **post):
        project = self._get_project_from_id(post.get("project_id"))
        if not project:
            return request.redirect("/tptr/cover-wizard?step=1&status=invalid_project")

        is_rhib = (project.template_tptr != "davits_rhib")
        if not is_rhib:
            selection_fields = [
                "prep_davit_inspector",
                "prep_davit_attendance",
                "prep_davit_document",
                "prep_davit_equipment",
                "davit_test_load",
                "davit_test_lifting",
                "davit_test_lowering",
                "davit_safe_relief_valve",
                "davit_safe_locking",
                "davit_safe_holding_valve",
                "davit_safe_stop_limit",
                "davit_safe_power_fail_brake",
                "davit_safe_space_heater",
                "davit_panel_alarm",
                "davit_panel_integration"
            ]
            write_vals = {}
            for field in selection_fields:
                val = (post.get(field) or "").strip().lower()
                if val not in {"ok", "not_ok"}:
                    val = "ok"
                write_vals[field] = val
                
            write_vals["davit_hoist_time_lift"] = (post.get("davit_hoist_time_lift") or "1.5").strip()
            write_vals["davit_hoist_press_lift"] = (post.get("davit_hoist_press_lift") or "140").strip()
            write_vals["davit_hoist_time_lower"] = (post.get("davit_hoist_time_lower") or "1.8").strip()
            write_vals["davit_hoist_press_lower"] = (post.get("davit_hoist_press_lower") or "150").strip()

            project.write(write_vals)

            # Clear and rebuild the remarks list dynamically
            catatan_remarks = request.httprequest.form.getlist("catatan_remark[]")
            catatan_actions = request.httprequest.form.getlist("catatan_action[]")

            catatan_remarks = [x.strip() for x in catatan_remarks if x is not None]
            catatan_actions = [x.strip() for x in catatan_actions if x is not None]

            project.catatan_ids.unlink()
            catatan_vals = []
            for i, (rem, act) in enumerate(zip(catatan_remarks, catatan_actions)):
                catatan_vals.append({
                    "kapal_id": project.id,
                    "remark": rem,
                    "action": act,
                    "sequence": (i + 1) * 10,
                })
            if catatan_vals:
                request.env["tptr.catatan"].create(catatan_vals)

            return request.redirect("/tptr/cover-wizard?step=9&project_id=%s&status=step8_saved" % project.id)

        # Retrieve all 22 checklist items
        write_vals = {}
        for i in range(1, 23):
            field_name = "prep_rhib_item%s" % i
            val = (post.get(field_name) or "").strip().lower()
            if val not in {"ok", "not_ok"}:
                val = "ok" # default fallback
            write_vals[field_name] = val

        project.write(write_vals)
        return request.redirect("/tptr/cover-wizard?step=9&project_id=%s&status=step8_saved" % project.id)

    # Simpan Step 9 (Review & Persetujuan), proses input selesai.
    @http.route("/tptr/cover-wizard/step9/save", type="http", auth="user", website=True, methods=["POST"], csrf=True)
    def tptr_cover_wizard_step9_save(self, **post):
        project = self._get_project_from_id(post.get("project_id"))
        if not project:
            return request.redirect("/tptr/cover-wizard?step=1&status=invalid_project")

        status_review_internal = (post.get("status_review_internal") or "").strip()
        status_review_class_owner_delegate = (post.get("status_review_class_owner_delegate") or "").strip()
        allowed_status = {"ya", "tidak"}

        if status_review_internal not in allowed_status or status_review_class_owner_delegate not in allowed_status:
            page_html = self._render_cover_wizard_page(
                step=9,
                project=project,
                error_message="Status review harus dipilih (Ya/Tidak).",
                form_data={
                    "status_review_internal": status_review_internal or "tidak",
                    "status_review_class_owner_delegate": status_review_class_owner_delegate or "tidak",
                    "tanda_tangan_shipyard": bool(post.get("tanda_tangan_shipyard")),
                    "tanda_tangan_class": bool(post.get("tanda_tangan_class")),
                    "tanda_tangan_owner_delegate": bool(post.get("tanda_tangan_owner_delegate")),
                },
            )
            return request.make_response(
                page_html,
                headers=[("Content-Type", "text/html; charset=utf-8")],
            )

        request.env["tptr.review_persetujuan"].create(
            {
                "tp_id": project.id,
                "status_review_internal": status_review_internal,
                "status_review_class_owner_delegate": status_review_class_owner_delegate,
                "tanda_tangan_shipyard": bool(post.get("tanda_tangan_shipyard")),
                "tanda_tangan_class": bool(post.get("tanda_tangan_class")),
                "tanda_tangan_owner_delegate": bool(post.get("tanda_tangan_owner_delegate")),
            }
        )
        return request.redirect("/tptr/cover-wizard?step=9&project_id=%s&status=completed" % project.id)

    # Halaman ini menampilkan form HTML murni untuk memilih proyek dan mengeksekusi download PDF Jasper.
    @http.route("/tptr/jasper-cover", type="http", auth="user", website=True, methods=["GET"])
    def jasper_cover_page(self, **kwargs):
        projects = request.env["pal.kapal.proyek"].search([], order="id desc")

        selected_project = None
        selected_id = (kwargs.get("project_id") or "").strip()
        if selected_id.isdigit():
            selected_project = request.env["pal.kapal.proyek"].browse(int(selected_id)).exists()
        if not selected_project and projects:
            selected_project = projects[0]

        status = kwargs.get("status")
        error_message = kwargs.get("error")
        page_html = self._render_jasper_cover_page(
            projects=projects,
            selected_project=selected_project,
            status=status,
            error_message=error_message,
        )
        return request.make_response(
            page_html,
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )

    # Endpoint POST ini memanggil service model Jasper lalu mengembalikan file PDF ke browser.
    @http.route(
        "/tptr/jasper-cover/download",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def jasper_cover_download(self, **post):
        project_id_raw = (post.get("project_id") or "").strip()
        if not project_id_raw.isdigit():
            return request.redirect("/tptr/jasper-cover?status=invalid_project")

        project_id = int(project_id_raw)
        project = request.env["pal.kapal.proyek"].browse(project_id).exists()
        if not project:
            return request.redirect("/tptr/jasper-cover?status=invalid_project")

        try:
            # Gunakan service model jika tersedia; fallback langsung ke method project
            # agar endpoint tetap berjalan saat proses Odoo belum me-reload model tptr.report.
            report_service = request.env.get("tptr.report")
            if report_service:
                pdf_content = report_service.generate_cover_sheet_pdf_by_id(project_id)
            else:
                pdf_content = project._get_jasper_combined_pdf()
        except UserError as exc:
            safe_error = quote_plus(str(exc))
            return request.redirect(
                "/tptr/jasper-cover?status=download_error&project_id=%s&error=%s"
                % (project_id, safe_error)
            )
        except Exception as exc:  # pragma: no cover - fallback untuk error tak terduga dari service eksternal.
            safe_error = quote_plus(str(exc))
            return request.redirect(
                "/tptr/jasper-cover?status=download_error&project_id=%s&error=%s"
                % (project_id, safe_error)
            )

        filename = "TPTR Document - %s.pdf" % (project.nomor_proyek or project.id)
        return request.make_response(
            pdf_content,
            headers=[
                ("Content-Type", "application/pdf"),
                ("Content-Length", str(len(pdf_content))),
                ("Content-Disposition", content_disposition(filename)),
            ],
        )

    # Halaman review terpisah untuk meninjau dokumen + mengisi form review/persetujuan.
    @http.route("/tptr/review-persetujuan", type="http", auth="user", website=True, methods=["GET"])
    def review_persetujuan_page(self, **kwargs):
        projects = request.env["pal.kapal.proyek"].search([], order="id desc")

        selected_project = None
        selected_id = (kwargs.get("project_id") or "").strip()
        if selected_id.isdigit():
            selected_project = request.env["pal.kapal.proyek"].browse(int(selected_id)).exists()
        if not selected_project and projects:
            selected_project = projects[0]

        status = kwargs.get("status")
        error_message = kwargs.get("error")
        page_html = self._render_review_persetujuan_page(
            projects=projects,
            selected_project=selected_project,
            status=status,
            error_message=error_message,
        )
        return request.make_response(
            page_html,
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )

    # Endpoint preview PDF inline untuk iframe pada halaman review.
    @http.route("/tptr/review-persetujuan/preview", type="http", auth="user", website=True, methods=["GET"])
    def review_persetujuan_preview(self, **kwargs):
        project_id_raw = (kwargs.get("project_id") or "").strip()
        if not project_id_raw.isdigit():
            return request.make_response(
                "Project tidak valid untuk preview.",
                headers=[("Content-Type", "text/plain; charset=utf-8")],
                status=400,
            )

        project = request.env["pal.kapal.proyek"].browse(int(project_id_raw)).exists()
        if not project:
            return request.make_response(
                "Project tidak ditemukan.",
                headers=[("Content-Type", "text/plain; charset=utf-8")],
                status=404,
            )

        try:
            report_service = request.env.get("tptr.report")
            if report_service:
                pdf_content = report_service.generate_cover_sheet_pdf_by_id(project.id)
            else:
                pdf_content = project._get_jasper_combined_pdf()
        except Exception as exc:
            return request.make_response(
                "Preview gagal dibuat: %s" % exc,
                headers=[("Content-Type", "text/plain; charset=utf-8")],
                status=500,
            )

        filename = "TPTR Document Preview - %s.pdf" % (project.nomor_proyek or project.id)
        return request.make_response(
            pdf_content,
            headers=[
                ("Content-Type", "application/pdf"),
                ("Content-Length", str(len(pdf_content))),
                ('Content-Disposition', 'inline; filename="%s"' % filename.replace('"', "")),
            ],
        )

    # Simpan hasil review/persetujuan dari halaman terpisah.
    @http.route("/tptr/review-persetujuan/save", type="http", auth="user", website=True, methods=["POST"], csrf=True)
    def review_persetujuan_save(self, **post):
        project_id_raw = (post.get("project_id") or "").strip()
        if not project_id_raw.isdigit():
            return request.redirect("/tptr/review-persetujuan?status=invalid_project")

        project = request.env["pal.kapal.proyek"].browse(int(project_id_raw)).exists()
        if not project:
            return request.redirect("/tptr/review-persetujuan?status=invalid_project")

        status_review_internal = (post.get("status_review_internal") or "").strip()
        status_review_class_owner_delegate = (post.get("status_review_class_owner_delegate") or "").strip()
        allowed_status = {"ya", "tidak"}

        form_data = {
            "status_review_internal": status_review_internal or "tidak",
            "status_review_class_owner_delegate": status_review_class_owner_delegate or "tidak",
            "tanda_tangan_shipyard": bool(post.get("tanda_tangan_shipyard")),
            "tanda_tangan_class": bool(post.get("tanda_tangan_class")),
            "tanda_tangan_owner_delegate": bool(post.get("tanda_tangan_owner_delegate")),
            "drawn_by_name": (post.get("drawn_by_name") or "").strip(),
            "designed_by_name": (post.get("designed_by_name") or "").strip(),
            "checked_by_name": (post.get("checked_by_name") or "").strip(),
            "approved_by_name": (post.get("approved_by_name") or "").strip(),
            "tanggal_drawn_by": (post.get("tanggal_drawn_by") or "").strip(),
            "tanggal_designed_by": (post.get("tanggal_designed_by") or "").strip(),
            "tanggal_checked_by": (post.get("tanggal_checked_by") or "").strip(),
            "tanggal_approved_by": (post.get("tanggal_approved_by") or "").strip(),
        }

        if status_review_internal not in allowed_status or status_review_class_owner_delegate not in allowed_status:
            projects = request.env["pal.kapal.proyek"].search([], order="id desc")
            page_html = self._render_review_persetujuan_page(
                projects=projects,
                selected_project=project,
                error_message="Status review harus dipilih Ya/Tidak.",
                form_data=form_data,
            )
            return request.make_response(
                page_html,
                headers=[("Content-Type", "text/html; charset=utf-8")],
            )

        request.env["tptr.review_persetujuan"].create(
            {
                "tp_id": project.id,
                "status_review_internal": form_data["status_review_internal"],
                "status_review_class_owner_delegate": form_data["status_review_class_owner_delegate"],
                "tanda_tangan_shipyard": form_data["tanda_tangan_shipyard"],
                "tanda_tangan_class": form_data["tanda_tangan_class"],
                "tanda_tangan_owner_delegate": form_data["tanda_tangan_owner_delegate"],
                "drawn_by_name": form_data["drawn_by_name"],
                "designed_by_name": form_data["designed_by_name"],
                "checked_by_name": form_data["checked_by_name"],
                "approved_by_name": form_data["approved_by_name"],
                "tanggal_drawn_by": form_data["tanggal_drawn_by"] or False,
                "tanggal_designed_by": form_data["tanggal_designed_by"] or False,
                "tanggal_checked_by": form_data["tanggal_checked_by"] or False,
                "tanggal_approved_by": form_data["tanggal_approved_by"] or False,
            }
        )
        return request.redirect("/tptr/review-persetujuan?project_id=%s&status=saved" % project.id)
