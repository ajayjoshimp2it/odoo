# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import base64

import werkzeug

from odoo import _, exceptions, http
from odoo.http import request
from odoo.tools import consteq


class MassMailController(http.Controller):

    @http.route(['/unsubscribe_from_list'], type='http', website=True, multilang=False, auth='public')
    def unsubscribe_placeholder_link(self, **post):
        """Dummy route so placeholder is not prefixed by language, MUST have multilang=False"""
        raise werkzeug.exceptions.NotFound()

    @http.route(['/mail/mailing/<int:mailing_id>/unsubscribe'], type='http', website=True, auth='public')
    def mailing(self, mailing_id, email=None, res_id=None, token="", **post):
        mailing = request.env['mail.mass_mailing'].sudo().browse(mailing_id)
        if mailing.exists():
            res_id = res_id and int(res_id)
            right_token = mailing._unsubscribe_token(res_id, email)
            if not consteq(str(token), right_token):
                raise exceptions.AccessDenied()

            if mailing.mailing_model_real == 'mail.mass_mailing.contact':
                # Unsubscribe directly + Let the user choose his subscriptions
                mailing.update_opt_out(email, mailing.contact_list_ids.ids, True)

                contacts = request.env['mail.mass_mailing.contact'].sudo().search([('email', '=', email)])
                subscription_list_ids = contacts.mapped('subscription_list_ids')
                # In many user are found : if user is opt_out on the list with contact_id 1 but not with contact_id 2,
                # assume that the user is not opt_out on both
                # TODO DBE Fixme : Optimise the following to get real opt_out and opt_in
                opt_out_list_ids = subscription_list_ids.filtered(lambda rel: rel.opt_out).mapped('list_id')
                opt_in_list_ids = subscription_list_ids.filtered(lambda rel: not rel.opt_out).mapped('list_id')
                opt_out_list_ids = set([list.id for list in opt_out_list_ids if list not in opt_in_list_ids])

                unique_list_ids = set([list.list_id.id for list in subscription_list_ids])
                list_ids = request.env['mail.mass_mailing.list'].sudo().browse(unique_list_ids)
                unsubscribed_list = ', '.join(str(list.name) for list in mailing.contact_list_ids if list.is_public)
                return request.render('mass_mailing.page_unsubscribe', {
                    'contacts': contacts,
                    'list_ids': list_ids,
                    'opt_out_list_ids': opt_out_list_ids,
                    'unsubscribed_list': unsubscribed_list,
                    'email': email,
                    'mailing_id': mailing_id,
                    'res_id': res_id,
                    'show_blacklist_button': request.env['ir.config_parameter'].sudo().get_param('mass_mailing.show_blacklist_buttons'),
                    })
            else:
                blacklist_rec = request.env['mail.blacklist'].sudo()._add(email)
                blacklist_rec._message_log(_("""The %s asked to not be contacted anymore 
                using an unsubscribe link.""" % request.env['ir.model']._get(mailing.mailing_model_real).display_name))
                return request.render('mass_mailing.page_unsubscribed', {
                    'email': email,
                    'mailing_id': mailing_id,
                    'res_id': res_id,
                    'show_blacklist_button': request.env['ir.config_parameter'].sudo().get_param(
                        'mass_mailing.show_blacklist_buttons'),
                    })
        return request.redirect('/web')

    @http.route('/mail/mailing/unsubscribe', type='json', auth='none')
    def unsubscribe(self, mailing_id, opt_in_ids, opt_out_ids, email, res_id, token):
        mailing = request.env['mail.mass_mailing'].sudo().browse(mailing_id)
        if mailing._unsubscribe_token(res_id, email) != token:
            return 'unauthorized'
        if mailing.exists():
            mailing.update_opt_out(email, opt_in_ids, False)
            mailing.update_opt_out(email, opt_out_ids, True)
            return True
        return 'error'

    @http.route('/mail/track/<int:mail_id>/blank.gif', type='http', auth='none')
    def track_mail_open(self, mail_id, **post):
        """ Email tracking. """
        request.env['mail.mail.statistics'].sudo().set_opened(mail_mail_ids=[mail_id])
        response = werkzeug.wrappers.Response()
        response.mimetype = 'image/gif'
        response.data = base64.b64decode(b'R0lGODlhAQABAIAAANvf7wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==')

        return response

    @http.route('/r/<string:code>/m/<int:stat_id>', type='http', auth="none")
    def full_url_redirect(self, code, stat_id, **post):
        # don't assume geoip is set, it is part of the website module
        # which mass_mailing doesn't depend on
        country_code = request.session.get('geoip', False) and request.session.geoip.get('country_code', False)

        request.env['link.tracker.click'].add_click(code, request.httprequest.remote_addr, country_code, stat_id=stat_id)
        return werkzeug.utils.redirect(request.env['link.tracker'].get_url_from_code(code), 301)

    @http.route('/mailing/blacklist/check', type='json', auth='none')
    def blacklist_check(self, mailing_id, res_id, email, token):
        mailing = request.env['mail.mass_mailing'].sudo().browse(mailing_id)
        if mailing._unsubscribe_token(res_id, email) != token:
            return 'unauthorized'
        if email:
            record = request.env['mail.blacklist'].sudo().with_context(active_test=False).search([('email', '=ilike', email)])
            if record['active']:
                return True
            return False
        return 'error'

    @http.route('/mailing/blacklist/add', type='json', auth='none')
    def blacklist_add(self, mailing_id, res_id, email, token):
        mailing = request.env['mail.mass_mailing'].sudo().browse(mailing_id)
        if mailing._unsubscribe_token(res_id, email) != token:
            return 'unauthorized'
        if email:
            blacklist_rec = request.env['mail.blacklist'].sudo()._add(email)
            blacklist_rec._message_log(_("""The %s asked to not be contacted anymore 
            using the unsubscription page.""" % request.env['ir.model']._get(mailing.mailing_model_real).display_name))
            return True
        return 'error'

    @http.route('/mailing/blacklist/remove', type='json', auth='none')
    def blacklist_remove(self, mailing_id, res_id, email, token):
        mailing = request.env['mail.mass_mailing'].sudo().browse(mailing_id)
        if mailing._unsubscribe_token(res_id, email) != token:
            return 'unauthorized'
        if email:
            request.env['mail.blacklist'].sudo()._remove(email)
            return True
        return 'error'

    @http.route('/mailing/feedback', type='json', auth='none')
    def send_feedback(self, mailing_id, res_id, email, feedback, token):
        mailing = request.env['mail.mass_mailing'].sudo().browse(mailing_id)
        if mailing._unsubscribe_token(res_id, email) != token:
            return 'unauthorized'
        if mailing.exists() and email:
            model = request.env[mailing.mailing_model_real]
            [email_field] = model._primary_email
            records = model.sudo().search([(email_field, '=ilike', email)])
            for record in records:
                record.sudo().message_post(body=_("Feedback from %s: %s" % (email, feedback)))
            return bool(records)
        return 'error'
