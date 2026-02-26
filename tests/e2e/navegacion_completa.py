#!/usr/bin/env python
"""
Script de navegación completa del aplicativo TransMaint.
Simula un usuario humano navegando por todas las secciones.
"""

import os
import sys
import time
from datetime import datetime

# Add project to path
sys.path.insert(0, '/home/user/Instelec')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


class NavigationReport:
    """Reporte de navegación."""

    def __init__(self):
        self.pages_visited = []
        self.errors = []
        self.warnings = []
        self.screenshots = []
        self.start_time = datetime.now()

    def add_visit(self, url, title, status):
        self.pages_visited.append({
            'url': url,
            'title': title,
            'status': status,
            'time': datetime.now().isoformat()
        })

    def add_error(self, url, error):
        self.errors.append({
            'url': url,
            'error': str(error),
            'time': datetime.now().isoformat()
        })

    def add_warning(self, url, warning):
        self.warnings.append({
            'url': url,
            'warning': warning,
            'time': datetime.now().isoformat()
        })

    def summary(self):
        duration = (datetime.now() - self.start_time).total_seconds()
        return {
            'total_pages': len(self.pages_visited),
            'errors': len(self.errors),
            'warnings': len(self.warnings),
            'duration_seconds': duration
        }


def run_navigation():
    """Ejecuta la navegación completa del aplicativo."""

    BASE_URL = "http://127.0.0.1:8000"
    report = NavigationReport()

    print("=" * 60)
    print("NAVEGACIÓN COMPLETA DEL APLICATIVO TRANSMAINT")
    print("=" * 60)
    print(f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"URL Base: {BASE_URL}")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            record_video_dir='/tmp/playwright_videos'
        )
        page = context.new_page()

        # Manejar errores de consola
        def handle_console(msg):
            if msg.type == 'error':
                report.add_warning(page.url, f"Console error: {msg.text}")

        page.on('console', handle_console)

        try:
            # ===== 1. VERIFICAR HEALTH CHECK =====
            print("\n[1/8] Verificando Health Check...")
            page.goto(f"{BASE_URL}/health/")
            content = page.content()
            if 'healthy' in content.lower():
                print("   ✓ Health check OK")
                report.add_visit(f"{BASE_URL}/health/", "Health Check", "OK")
            else:
                print("   ✗ Health check FAILED")
                report.add_error(f"{BASE_URL}/health/", "Health check no devolvió 'healthy'")

            # ===== 2. VERIFICAR API HEALTH =====
            print("\n[2/8] Verificando API Health...")
            page.goto(f"{BASE_URL}/api/health/")
            content = page.content()
            if 'healthy' in content.lower():
                print("   ✓ API Health OK")
                report.add_visit(f"{BASE_URL}/api/health/", "API Health", "OK")
            else:
                report.add_error(f"{BASE_URL}/api/health/", "API Health check failed")

            # ===== 3. ACCEDER A LOGIN =====
            print("\n[3/8] Accediendo a página de login...")
            page.goto(f"{BASE_URL}/usuarios/login/")
            page.wait_for_load_state('networkidle')

            # Verificar elementos del formulario
            title = page.title()
            print(f"   Título: {title}")

            # Buscar campos del formulario
            username_input = page.locator("input[name='username'], input[name='email'], input[type='email']").first
            password_input = page.locator("input[name='password'], input[type='password']").first
            submit_btn = page.locator("button[type='submit'], input[type='submit']").first

            if username_input.is_visible() and password_input.is_visible():
                print("   ✓ Formulario de login visible")
                report.add_visit(f"{BASE_URL}/usuarios/login/", title, "OK")
            else:
                print("   ✗ Campos de formulario no encontrados")
                report.add_error(f"{BASE_URL}/usuarios/login/", "Campos de login no visibles")

            # Screenshot de login
            page.screenshot(path='/tmp/login_page.png')
            report.screenshots.append('/tmp/login_page.png')
            print("   📸 Screenshot: /tmp/login_page.png")

            # ===== 4. INICIAR SESIÓN =====
            print("\n[4/8] Iniciando sesión como admin...")
            username_input.fill("admin@transmaint.com")
            password_input.fill("Admin123!")
            submit_btn.click()

            page.wait_for_load_state('networkidle')
            time.sleep(1)

            current_url = page.url
            if '/login' not in current_url or 'next=' in current_url:
                print(f"   ✓ Login exitoso - Redirigido a: {current_url}")
                report.add_visit(current_url, "Post-Login", "OK")
            else:
                print(f"   ✗ Login fallido - Aún en: {current_url}")
                report.add_error(current_url, "Login no redirigió correctamente")
                # Intentar ver mensaje de error
                error_msg = page.locator(".alert-danger, .error, .errorlist").first
                if error_msg.is_visible():
                    print(f"   Error mostrado: {error_msg.text_content()}")

            page.screenshot(path='/tmp/after_login.png')
            report.screenshots.append('/tmp/after_login.png')

            # ===== 5. NAVEGAR POR MÓDULOS =====
            print("\n[5/8] Navegando por módulos principales...")

            modules = [
                ("/", "Home/Dashboard"),
                ("/actividades/", "Actividades"),
                ("/cuadrillas/", "Cuadrillas"),
                ("/lineas/", "Líneas"),
                ("/campo/", "Campo"),
                ("/indicadores/", "Indicadores"),
            ]

            for path, name in modules:
                try:
                    url = f"{BASE_URL}{path}"
                    print(f"\n   Navegando a {name}...")
                    page.goto(url)
                    page.wait_for_load_state('networkidle', timeout=10000)

                    current = page.url
                    title = page.title()

                    # Verificar si fuimos redirigidos a login
                    if '/login' in current and 'next=' in current:
                        print(f"   ⚠ {name}: Requiere autenticación (redirigido a login)")
                        report.add_warning(url, "Requiere autenticación")
                    elif '/login' in current:
                        print(f"   ✗ {name}: No autenticado")
                        report.add_error(url, "Sesión no activa")
                    else:
                        print(f"   ✓ {name}: Accesible ({current})")
                        report.add_visit(url, title or name, "OK")

                        # Screenshot
                        screenshot_path = f'/tmp/module_{name.lower().replace("/", "_")}.png'
                        page.screenshot(path=screenshot_path)
                        report.screenshots.append(screenshot_path)

                except PlaywrightTimeout:
                    print(f"   ✗ {name}: Timeout")
                    report.add_error(f"{BASE_URL}{path}", "Timeout al cargar página")
                except Exception as e:
                    print(f"   ✗ {name}: Error - {str(e)}")
                    report.add_error(f"{BASE_URL}{path}", str(e))

            # ===== 6. VERIFICAR API ENDPOINTS =====
            print("\n[6/8] Verificando endpoints API...")

            api_endpoints = [
                "/api/lineas/",
                "/api/cuadrillas/",
                "/api/actividades/",
                "/api/campo/registros/",
                "/api/indicadores/",
            ]

            for endpoint in api_endpoints:
                try:
                    url = f"{BASE_URL}{endpoint}"
                    response = page.goto(url)
                    status = response.status if response else 0

                    if status == 200:
                        print(f"   ✓ {endpoint}: OK (200)")
                        report.add_visit(url, f"API {endpoint}", "OK")
                    elif status == 401:
                        print(f"   ⚠ {endpoint}: No autorizado (401)")
                        report.add_warning(url, "Requiere autenticación JWT")
                    elif status == 403:
                        print(f"   ⚠ {endpoint}: Prohibido (403)")
                        report.add_warning(url, "Acceso prohibido")
                    else:
                        print(f"   ✗ {endpoint}: Error ({status})")
                        report.add_error(url, f"HTTP {status}")

                except Exception as e:
                    print(f"   ✗ {endpoint}: {str(e)}")
                    report.add_error(f"{BASE_URL}{endpoint}", str(e))

            # ===== 7. VERIFICAR PÁGINA DE ADMIN =====
            print("\n[7/8] Verificando Django Admin...")
            try:
                page.goto(f"{BASE_URL}/admin/")
                page.wait_for_load_state('networkidle')

                if 'Django' in page.title() or 'admin' in page.url.lower():
                    print("   ✓ Django Admin accesible")
                    report.add_visit(f"{BASE_URL}/admin/", "Django Admin", "OK")
                    page.screenshot(path='/tmp/admin_page.png')
                    report.screenshots.append('/tmp/admin_page.png')
                else:
                    print("   ⚠ Django Admin redirige a otro lugar")

            except Exception as e:
                print(f"   ✗ Error en admin: {str(e)}")
                report.add_error(f"{BASE_URL}/admin/", str(e))

            # ===== 8. PROBAR FLUJO DE LOGOUT =====
            print("\n[8/8] Verificando flujo de logout...")
            try:
                # Buscar boton de logout (ahora es un form POST)
                logout_btn = page.locator("button:has-text('Cerrar Sesion')").first
                if logout_btn.is_visible():
                    logout_btn.click()
                    page.wait_for_load_state('networkidle')
                    print(f"   ✓ Logout ejecutado - URL: {page.url}")
                    report.add_visit(page.url, "Logout", "OK")
                else:
                    # Fallback: enviar POST directamente
                    page.evaluate("""
                        fetch('/usuarios/logout/', {
                            method: 'POST',
                            headers: {'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || ''},
                            credentials: 'same-origin'
                        }).then(() => window.location.href = '/usuarios/login/')
                    """)
                    page.wait_for_load_state('networkidle')
                    print(f"   ✓ Logout directo via POST - URL: {page.url}")

            except Exception as e:
                print(f"   ⚠ No se pudo probar logout: {str(e)}")
                report.add_warning(f"{BASE_URL}/usuarios/logout/", str(e))

        except Exception as e:
            print(f"\n❌ Error crítico: {str(e)}")
            report.add_error("CRITICAL", str(e))

        finally:
            context.close()
            browser.close()

    # ===== REPORTE FINAL =====
    print("\n" + "=" * 60)
    print("REPORTE DE NAVEGACIÓN")
    print("=" * 60)

    summary = report.summary()
    print(f"\nPáginas visitadas: {summary['total_pages']}")
    print(f"Errores encontrados: {summary['errors']}")
    print(f"Advertencias: {summary['warnings']}")
    print(f"Duración: {summary['duration_seconds']:.2f} segundos")

    if report.errors:
        print("\n--- ERRORES ---")
        for err in report.errors:
            print(f"  • {err['url']}: {err['error']}")

    if report.warnings:
        print("\n--- ADVERTENCIAS ---")
        for warn in report.warnings:
            print(f"  • {warn['url']}: {warn['warning']}")

    print("\n--- SCREENSHOTS ---")
    for ss in report.screenshots:
        print(f"  📸 {ss}")

    print("\n" + "=" * 60)
    print(f"Fin: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    return report


if __name__ == "__main__":
    report = run_navigation()

    # Exit code basado en errores críticos
    if any('CRITICAL' in e['url'] for e in report.errors):
        sys.exit(1)
    sys.exit(0)
