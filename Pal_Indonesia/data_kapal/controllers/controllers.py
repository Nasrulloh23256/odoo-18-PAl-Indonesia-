# -*- coding: utf-8 -*-
# from odoo import http


# class DataKapal(http.Controller):
#     @http.route('/data_kapal/data_kapal', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/data_kapal/data_kapal/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('data_kapal.listing', {
#             'root': '/data_kapal/data_kapal',
#             'objects': http.request.env['data_kapal.data_kapal'].search([]),
#         })

#     @http.route('/data_kapal/data_kapal/objects/<model("data_kapal.data_kapal"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('data_kapal.object', {
#             'object': obj
#         })

