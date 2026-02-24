from odoo import _, models
from odoo.exceptions import UserError


# Service model untuk menjembatani controller web dengan generator PDF Jasper di model proyek/kapal.
class TPTRReportService(models.AbstractModel):
    _name = "tptr.report"
    _description = "TPTR Jasper Report Service"

    # Controller memanggil method ini untuk menghasilkan PDF cover sheet dari Jasper Server eksternal.
    def generate_cover_sheet_pdf(self, project):
        project.ensure_one()
        return project._get_jasper_cover_sheet_pdf()

    # Helper ini menerima project_id dari controller agar validasi record bisa dipusatkan di service layer.
    def generate_cover_sheet_pdf_by_id(self, project_id):
        if not project_id:
            raise UserError(_("Project belum dipilih."))

        project = self.env["pal.kapal.proyek"].browse(project_id).exists()
        if not project:
            raise UserError(_("Data project/kapal tidak ditemukan atau tidak dapat diakses."))
        return self.generate_cover_sheet_pdf(project)
