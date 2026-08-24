"""Tests for the brand skin over the Django admin.

The admin is styled by redefining the CSS variables Django already declares, in
``static/cc_admin/css/brand.css``. Next.js and Django share no build step, so the
palette is written out twice -- once in ``frontend/app/globals.css`` and once in
brand.css -- and nothing in either file would notice if the two drifted apart.
That is what the first test is for. globals.css is the source of truth.

The rest guards the two things a Django upgrade could quietly break: the template
override still has to render (a renamed block in ``admin/base.html`` would leave the
stylesheet unloaded and the admin silently un-branded), and dark mode still has to
stay switched off, because the brand has no dark palette to switch to.
"""
import re
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from app.accounts.models import User, UserStatus

BRAND_CSS = Path(settings.BASE_DIR) / 'static' / 'cc_admin' / 'css' / 'brand.css'
GLOBALS_CSS = Path(settings.BASE_DIR) / 'frontend' / 'app' / 'globals.css'

# The palette colours, by the name each file gives them. Semantic aliases in
# globals.css (--color-primary and friends) are not compared: the admin maps the
# palette onto Django's own variable names instead, so there is nothing to line up.
SHARED_TOKENS = (
    'forest-green',
    'forest-green-deep',
    'olive-green',
    'sage-green',
    'cream-warm',
    'cream-cool',
    'bark',
    'bark-light',
    'clay-red',
)

PASSWORD = 'Str0ng-Passphrase!'


def declared_colours(path, prefix):
    """Map token name -> lowercase hex, for the ``--{prefix}{name}: #hex;`` lines."""
    pattern = re.compile(
        r'--' + re.escape(prefix) + r'([a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{3,8})\s*;'
    )
    return {
        name: value.lower()
        for name, value in pattern.findall(path.read_text(encoding='utf-8'))
    }


class PaletteTests(TestCase):
    def test_admin_palette_matches_the_frontend(self):
        """Every shared colour is the same hex on both sides.

        A failure here means the palette moved in one file and not the other. Fix
        it by copying the value from globals.css, which is the source of truth.
        """
        frontend = declared_colours(GLOBALS_CSS, 'color-')
        admin = declared_colours(BRAND_CSS, 'cc-')

        for token in SHARED_TOKENS:
            with self.subTest(token=token):
                self.assertIn(token, frontend, f'{token} is missing from globals.css')
                self.assertIn(token, admin, f'{token} is missing from brand.css')
                self.assertEqual(
                    admin[token],
                    frontend[token],
                    f'--cc-{token} in brand.css disagrees with '
                    f'--color-{token} in globals.css',
                )

class StylesheetRuleTests(TestCase):
    """Two rules in brand.css that are easy to break and invisible when broken."""

    @staticmethod
    def without_comments():
        return re.sub(
            r'/\*.*?\*/', '', BRAND_CSS.read_text(encoding='utf-8'), flags=re.S
        )

    def test_olive_green_is_never_a_text_or_button_colour(self):
        """Olive is 2.99:1 on white, so it cannot carry text anywhere.

        brand.css spends it on focus rings and borders only. This catches a later
        edit that reaches for it as a fill or a foreground.
        """
        css = self.without_comments()
        for variable in (
            '--button-bg', '--default-button-bg', '--body-fg', '--link-fg',
            '--header-bg', '--primary-fg', '--button-fg', '--object-tools-bg',
        ):
            with self.subTest(variable=variable):
                declared = re.search(re.escape(variable) + r'\s*:\s*([^;]+);', css)
                self.assertIsNotNone(declared, f'{variable} is not declared')
                self.assertNotIn('olive', declared.group(1))

    def test_no_clipping_ancestors(self):
        """Rounding a card is the obvious way to reintroduce a clipped date picker.

        Django opens the calendar for date_of_birth as a position: absolute
        .calendarbox inside the same fieldset that holds the field. Any ancestor
        with a non-visible overflow cuts it off, and the natural way to round a card
        is to add `overflow: hidden` to clip its corners. So brand.css rounds the
        headers instead and declares no overflow at all. Nothing in the rendered
        page would look wrong until someone opens a date field.
        """
        self.assertNotIn(
            'overflow',
            self.without_comments(),
            'brand.css declares overflow: a clipping ancestor breaks the date '
            'picker. Round the card header instead of clipping the card.',
        )

    def test_login_rules_outrank_login_css(self):
        """login.css is the one admin stylesheet that loads after brand.css.

        At equal specificity it wins on source order, so brand.css qualifies its
        login selectors with `body`. Dropping that prefix makes these rules dead
        without changing anything else about the file.
        """
        css = self.without_comments()
        self.assertIn('body.login {', css)
        self.assertIn('body.login #container {', css)
        self.assertNotRegex(css, r'(?<!body)\.login #container\s*\{')


class StaticFileTests(TestCase):
    def test_every_referenced_asset_resolves(self):
        """The stylesheet, its fonts and the badge are all findable by staticfiles.

        Without STATICFILES_DIRS these return None and the admin renders unstyled
        with a broken logo, which is easy to miss in a diff and obvious in a browser.
        """
        assets = [
            'cc_admin/css/brand.css',
            'cc_admin/img/logo-badge-on-green.png',
            'cc_admin/fonts/dm-sans-latin.woff2',
            'cc_admin/fonts/dm-sans-latin-ext.woff2',
            'cc_admin/fonts/playfair-display-latin.woff2',
            'cc_admin/fonts/playfair-display-latin-ext.woff2',
        ]
        for asset in assets:
            with self.subTest(asset=asset):
                self.assertIsNotNone(finders.find(asset), f'{asset} is not on the path')

    def test_font_urls_in_the_stylesheet_point_at_real_files(self):
        """The @font-face src paths are relative to the stylesheet, not to STATIC_URL.

        Getting that wrong fails silently: the browser falls back to the generic
        stack and the admin merely looks slightly off.
        """
        css = BRAND_CSS.read_text(encoding='utf-8')
        references = re.findall(r'url\("([^"]+\.woff2)"\)', css)
        self.assertEqual(len(references), 4, 'expected four @font-face sources')
        for reference in references:
            with self.subTest(reference=reference):
                self.assertTrue(
                    (BRAND_CSS.parent / reference).resolve().is_file(),
                    f'{reference} does not resolve to a file',
                )


class RenderedAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser(
            email='staff@example.com',
            password=PASSWORD,
            status=UserStatus.ACTIVE,
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def test_index_loads_the_brand_stylesheet(self):
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'cc_admin/css/brand.css')

    def test_index_renders_the_badge_and_wordmark(self):
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, 'cc_admin/img/logo-badge-on-green.png')
        self.assertContains(response, 'Cultivators Collective')
        self.assertNotContains(response, 'Django administration')

    def test_title_block_survives_the_template_override(self):
        """base.html defines `title` as empty, so base_site.html has to declare it.

        Dropping it from the override leaves every admin page with a blank tab.
        """
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, '<title>')
        self.assertContains(response, 'Cultivators Collective admin')

    def test_dark_mode_is_not_shipped(self):
        """The brand has no dark palette, so neither asset may be loaded.

        theme.js is the other half: it writes data-theme onto <html> from
        localStorage, which outranks the :root variables in brand.css.
        """
        response = self.client.get(reverse('admin:index'))
        self.assertNotContains(response, 'admin/css/dark_mode.css')
        self.assertNotContains(response, 'admin/js/theme.js')

    def test_changelist_and_change_form_render(self):
        """The member screens are the ones staff actually use.

        A template override that breaks a block Django expects usually shows up
        here rather than on the index.
        """
        changelist = self.client.get(reverse('admin:accounts_user_changelist'))
        self.assertEqual(changelist.status_code, 200)
        self.assertContains(changelist, 'cc_admin/css/brand.css')

        change = self.client.get(
            reverse('admin:accounts_user_change', args=[self.staff.pk])
        )
        self.assertEqual(change.status_code, 200)
        self.assertContains(change, 'cc_admin/css/brand.css')

    def test_login_page_is_branded_for_anonymous_visitors(self):
        """The one admin page an unauthenticated member could reach."""
        self.client.logout()
        response = self.client.get(reverse('admin:login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'cc_admin/css/brand.css')
        self.assertNotContains(response, 'admin/js/theme.js')
