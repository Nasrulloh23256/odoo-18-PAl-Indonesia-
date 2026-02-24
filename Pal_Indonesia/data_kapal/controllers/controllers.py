# -*- coding: utf-8 -*-

import base64
import html
from typing import Any, Dict, Mapping, Optional
from urllib.parse import quote_plus

from odoo import http
from odoo.exceptions import UserError
from odoo.http import content_disposition, request
from odoo.modules.module import get_module_resource


# Controller website ini menyediakan halaman CRUD Data Kapal & Proyek untuk user internal.
class DataKapalWebsiteController(http.Controller):
    # Helper ini menyiapkan payload write/create dari data form agar konsisten antar route.
    def _build_payload(self, post: Mapping[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "nama_kapal": (post.get("nama_kapal") or "").strip(),
            "nomor_proyek": (post.get("nomor_proyek") or "").strip(),
            "delegasi_pemilik": (post.get("delegasi_pemilik") or "").strip(),
            "jenis_tes": (post.get("jenis_tes") or "").strip(),
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
        }

        if record:
            base_data.update(
                {
                    "nama_kapal": record.nama_kapal or "",
                    "nomor_proyek": record.nomor_proyek or "",
                    "kelas_kapal_id": record.kelas_kapal_id.id or "",
                    "delegasi_pemilik": record.delegasi_pemilik or "",
                    "jenis_tes": record.jenis_tes or "hat",
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
            rows.append(
                (
                    "<tr>"
                    "<td>{nama_kapal}</td>"
                    "<td>{nomor_proyek}</td>"
                    "<td>{kelas_kapal}</td>"
                    "<td>{delegasi_pemilik}</td>"
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
                    jenis_tes=html.escape(jenis_tes, quote=True),
                    tanggal_input=html.escape(str(rec.tanggal_input or ""), quote=True),
                    csrf_token=html.escape(csrf_token, quote=True),
                )
            )

        if not rows:
            rows.append('<tr><td colspan="7" class="empty-row">Belum ada data.</td></tr>')

        jenis_tes = values["form_data"].get("jenis_tes") or "hat"
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

    # Cegah user loncat step sebelum step sebelumnya selesai.
    def _guard_wizard_step(self, step: int, project: Any):
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
            "completed": ("success", "Semua step selesai. Data cover TPTR siap dipakai."),
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
            (4, "Review & Persetujuan", "Status review dan tanda tangan."),
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

    # Ringkasan project aktif agar user selalu tahu konteks project yang sedang diisi.
    def _build_cover_wizard_project_summary(self, project: Any) -> str:
        if not project:
            return (
                '<section class="wizard-project-summary empty">'
                '<h2>Project Aktif</h2>'
                '<p>Belum ada project aktif. Mulai dari Step 1 untuk membuat data baru.</p>'
                "</section>"
            )

        lokasi_count = request.env["tptr.lokasi_kelas"].search_count([("kapal_id", "=", project.id)])
        dokumen_count = request.env["tptr.dokumen_pendukung"].search_count([("tp_id", "=", project.id)])
        review_count = request.env["tptr.review_persetujuan"].search_count([("tp_id", "=", project.id)])

        return (
            '<section class="wizard-project-summary">'
            '<h2>Project Aktif: {project}</h2>'
            '<div class="wizard-project-grid">'
            '<article><span>Nomor Proyek</span><strong>{project_no}</strong></article>'
            '<article><span>Kelas Kapal</span><strong>{kelas}</strong></article>'
            '<article><span>Delegasi Pemilik</span><strong>{owner}</strong></article>'
            '<article><span>Progress Data</span><strong>L{lokasi} / D{dokumen} / R{review}</strong></article>'
            "</div>"
            '<div class="wizard-project-actions">'
            '<a class="wizard-btn wizard-btn-soft" href="/tptr/jasper-cover?project_id={id}">Buka Jasper Cover</a>'
            '<a class="wizard-btn wizard-btn-soft" href="/web#id={id}&model=pal.kapal.proyek&view_type=form">Buka Form Backend</a>'
            "</div>"
            "</section>"
        ).format(
            project=html.escape(project.nama_kapal or "-", quote=True),
            project_no=html.escape(project.nomor_proyek or "-", quote=True),
            kelas=html.escape(project.kelas_kapal or "-", quote=True),
            owner=html.escape(project.delegasi_pemilik or "-", quote=True),
            lokasi=lokasi_count,
            dokumen=dokumen_count,
            review=review_count,
            id=project.id,
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
            label = "%s - %s" % (project.nomor_proyek or "-", project.nama_kapal or "Tanpa Nama")
            options.append(
                '<option value="{id}"{selected}>{label}</option>'.format(
                    id=project.id,
                    selected=selected_attr,
                    label=html.escape(label, quote=True),
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
    ) -> str:
        form_data = dict(form_data or {})

        if step == 1:
            kelas_records = request.env["pal.kapal.kelas"].search([], order="name asc")
            if project and not form_data:
                form_data = {
                    "project_id": project.id,
                    "nama_kapal": project.nama_kapal or "",
                    "nomor_proyek": project.nomor_proyek or "",
                    "kelas_kapal_id": project.kelas_kapal_id.id or "",
                    "delegasi_pemilik": project.delegasi_pemilik or "",
                    "jenis_tes": project.jenis_tes or "hat",
                }
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

            hidden_project = ""
            if form_data.get("project_id"):
                hidden_project = (
                    '<input type="hidden" name="project_id" value="%s" />'
                    % html.escape(str(form_data.get("project_id")), quote=True)
                )

            return (
                '<h2>Step 1: Data Kapal &amp; Proyek</h2>'
                '<p class="wizard-help">Simpan data dasar untuk membuka step berikutnya.</p>'
                '<form method="post" action="/tptr/cover-wizard/step1/save" enctype="multipart/form-data" class="wizard-form">'
                '<input type="hidden" name="csrf_token" value="{csrf}" />'
                "{hidden_project}"
                '<div class="wizard-grid">'
                '<label><span>Nama Kapal</span><input type="text" name="nama_kapal" required value="{nama_kapal}" /></label>'
                '<label><span>Nomor Proyek</span><input type="text" name="nomor_proyek" required value="{nomor_proyek}" /></label>'
                '<label><span>Kelas Kapal</span><select name="kelas_kapal_id" required>{kelas_options}</select></label>'
                '<label><span>Delegasi Pemilik</span><input type="text" name="delegasi_pemilik" required value="{delegasi_pemilik}" /></label>'
                '<label><span>Jenis Tes</span><select name="jenis_tes">'
                '<option value="hat"{hat_selected}>HAT</option>'
                '<option value="sat"{sat_selected}>SAT</option>'
                "</select></label>"
                '<label><span>Project Symbol (Opsional)</span><input type="file" name="project_symbol" accept="image/*" /></label>'
                "</div>"
                '<div class="wizard-actions"><button type="submit" class="wizard-btn wizard-btn-primary">Simpan &amp; Lanjut Step 2</button></div>'
                "</form>"
            ).format(
                csrf=html.escape(csrf_token, quote=True),
                hidden_project=hidden_project,
                nama_kapal=html.escape(form_data.get("nama_kapal") or "", quote=True),
                nomor_proyek=html.escape(form_data.get("nomor_proyek") or "", quote=True),
                kelas_options="".join(options),
                delegasi_pemilik=html.escape(form_data.get("delegasi_pemilik") or "", quote=True),
                hat_selected=' selected="selected"' if (form_data.get("jenis_tes") or "hat") == "hat" else "",
                sat_selected=' selected="selected"' if (form_data.get("jenis_tes") or "hat") == "sat" else "",
            )

        if not project:
            return (
                '<h2>Project belum tersedia</h2>'
                '<p class="wizard-help">Silakan isi Step 1 terlebih dahulu.</p>'
            )

        if step == 2:
            sign_checked = " checked" if form_data.get("sign_class") else ""
            return (
                '<h2>Step 2: Lokasi &amp; Kelas Pengujian</h2>'
                '<p class="wizard-help">Isi lokasi pengujian untuk project aktif.</p>'
                '<form method="post" action="/tptr/cover-wizard/step2/save" class="wizard-form">'
                '<input type="hidden" name="csrf_token" value="{csrf}" />'
                '<input type="hidden" name="project_id" value="{project_id}" />'
                '<div class="wizard-grid">'
                '<label><span>Lokasi Pengujian</span><input type="text" name="lokasi_pengujian" required value="{lokasi}" /></label>'
                '<label class="wizard-checkbox"><input type="checkbox" name="sign_class"{checked} /><span>Sign Class</span></label>'
                '<label class="wizard-span-2"><span>Catatan</span><textarea name="note" rows="4">{note}</textarea></label>'
                "</div>"
                '<div class="wizard-actions"><button type="submit" class="wizard-btn wizard-btn-primary">Simpan &amp; Lanjut Step 3</button></div>'
                "</form>"
            ).format(
                csrf=html.escape(csrf_token, quote=True),
                project_id=project.id,
                lokasi=html.escape(form_data.get("lokasi_pengujian") or "", quote=True),
                checked=sign_checked,
                note=html.escape(form_data.get("note") or "", quote=True),
            )

        if step == 3:
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

        status_internal = form_data.get("status_review_internal") or "tidak"
        status_class_owner = form_data.get("status_review_class_owner_delegate") or "tidak"
        shipyard_checked = " checked" if form_data.get("tanda_tangan_shipyard") else ""
        class_checked = " checked" if form_data.get("tanda_tangan_class") else ""
        owner_checked = " checked" if form_data.get("tanda_tangan_owner_delegate") else ""

        return (
            '<h2>Step 4: Review &amp; Persetujuan</h2>'
            '<p class="wizard-help">Lengkapi status review dan tanda tangan persetujuan.</p>'
            '<form method="post" action="/tptr/cover-wizard/step4/save" class="wizard-form">'
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
        if step != 4 or status != "completed" or not project:
            return ""
        return (
            '<section class="wizard-final">'
            '<h3>Pengisian selesai</h3>'
            "<p>Data cover TPTR sudah lengkap. Lanjutkan ke halaman Jasper untuk unduh PDF.</p>"
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
    ) -> str:
        template_html = self._load_cover_wizard_template()
        csrf_token = request.csrf_token()

        replacements = {
            "__STATUS_BLOCK__": self._build_cover_wizard_status_block(
                status=status,
                error_message=error_message,
                warning_message=warning_message,
            ),
            "__STEP_TRACKER__": self._build_cover_wizard_stepper(step, project),
            "__PROJECT_SUMMARY__": self._build_cover_wizard_project_summary(project),
            "__RESUME_OPTIONS__": self._build_cover_wizard_resume_options(project),
            "__STEP_FORM__": self._build_cover_wizard_step_form(step, project, csrf_token, form_data=form_data),
            "__FINAL_ACTIONS__": self._build_cover_wizard_final_actions(step, status, project),
            "__STEP_VALUE__": str(step),
            "__PROJECT_ID_VALUE__": str(project.id) if project else "",
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
        step_raw = (kwargs.get("step") or "1").strip()
        step = int(step_raw) if step_raw.isdigit() and 1 <= int(step_raw) <= 4 else 1
        project = self._get_project_from_id(kwargs.get("project_id"))

        guarded_step, warning_message = self._guard_wizard_step(step, project)
        step = guarded_step

        page_html = self._render_cover_wizard_page(
            step=step,
            project=project,
            status=kwargs.get("status"),
            error_message=kwargs.get("error"),
            warning_message=warning_message,
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

        lokasi_pengujian = (post.get("lokasi_pengujian") or "").strip()
        note = (post.get("note") or "").strip()
        sign_class = bool(post.get("sign_class"))

        if not lokasi_pengujian:
            page_html = self._render_cover_wizard_page(
                step=2,
                project=project,
                error_message="Lokasi Pengujian wajib diisi.",
                form_data={
                    "lokasi_pengujian": lokasi_pengujian,
                    "note": note,
                    "sign_class": sign_class,
                },
            )
            return request.make_response(
                page_html,
                headers=[("Content-Type", "text/html; charset=utf-8")],
            )

        request.env["tptr.lokasi_kelas"].create(
            {
                "kapal_id": project.id,
                "lokasi_pengujian": lokasi_pengujian,
                "sign_class": sign_class,
                "note": note,
            }
        )
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

    # Simpan Step 4 (Review & Persetujuan), proses input selesai.
    @http.route("/tptr/cover-wizard/step4/save", type="http", auth="user", website=True, methods=["POST"], csrf=True)
    def tptr_cover_wizard_step4_save(self, **post):
        project = self._get_project_from_id(post.get("project_id"))
        if not project:
            return request.redirect("/tptr/cover-wizard?step=1&status=invalid_project")

        status_review_internal = (post.get("status_review_internal") or "").strip()
        status_review_class_owner_delegate = (post.get("status_review_class_owner_delegate") or "").strip()
        allowed_status = {"ya", "tidak"}

        if status_review_internal not in allowed_status or status_review_class_owner_delegate not in allowed_status:
            page_html = self._render_cover_wizard_page(
                step=4,
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
        return request.redirect("/tptr/cover-wizard?step=4&project_id=%s&status=completed" % project.id)

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
                pdf_content = project._get_jasper_cover_sheet_pdf()
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

        filename = "Cover Sheet Jasper - %s.pdf" % (project.nomor_proyek or project.id)
        return request.make_response(
            pdf_content,
            headers=[
                ("Content-Type", "application/pdf"),
                ("Content-Length", str(len(pdf_content))),
                ("Content-Disposition", content_disposition(filename)),
            ],
        )
