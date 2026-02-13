# -*- coding: utf-8 -*-

from odoo import fields, models


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
