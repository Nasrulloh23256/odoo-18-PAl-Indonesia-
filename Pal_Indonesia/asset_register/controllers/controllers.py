# -*- coding: utf-8 -*-
# from odoo import http


# class AssetRegister(http.Controller):
#     @http.route('/asset__register/asset__register', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/asset__register/asset__register/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('asset__register.listing', {
#             'root': '/asset__register/asset__register',
#             'objects': http.request.env['asset__register.asset__register'].search([]),
#         })

#     @http.route('/asset__register/asset__register/objects/<model("asset__register.asset__register"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('asset__register.object', {
#             'object': obj
#         })

