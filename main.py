import os
import ssl
from app import create_app
import platform
from pathlib import Path
from dotenv import load_dotenv


load_dotenv(dotenv_path=Path(__file__).resolve().with_name(".env"))


def _get_env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main():
    app = create_app()
    debug_enabled = app.config.get('DEBUG', False)
    use_reloader = _get_env_bool('APP_USE_RELOADER', debug_enabled)

    use_https = app.config.get('USE_HTTPS', False)
    server_port = app.config.get('SERVER_PORT', 5000)
    server_host = app.config.get('SERVER_HOST', '0.0.0.0')

    if use_https:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        system = platform.system().lower()
        if system == 'windows':
            ssl_dir = Path(app.root_path).parent / 'ssl'
            ssl_dir.mkdir(parents=True, exist_ok=True)
            cert_path = str(ssl_dir / 'home-cloud.crt')
            key_path = str(ssl_dir / 'home-cloud.key')
        else:
            cert_path = '/etc/ssl/certs/home-cloud.crt'
            key_path = '/etc/ssl/private/home-cloud.key'

        cert_path = app.config.get('SSL_CERT', cert_path)
        key_path = app.config.get('SSL_KEY', key_path)

        if not os.path.exists(cert_path) or not os.path.exists(key_path):
            print(f"Warning: SSL certificate files not found at {cert_path} and {key_path}")
            print("Running without HTTPS. Please configure SSL certificates for secure operation.")
            app.run(debug=debug_enabled, host=server_host, port=server_port, use_reloader=use_reloader)
            return

        try:
            context.load_cert_chain(cert_path, key_path)
            app.ssl_context = context
            app.run(
                debug=debug_enabled,
                host=server_host,
                port=server_port,
                ssl_context=context,
                use_reloader=use_reloader,
            )
            return
        except Exception as e:
            print(f"Error loading SSL certificates: {e}")
            print("Running without HTTPS. Please check your SSL configuration.")

    app.run(debug=debug_enabled, host=server_host, port=server_port, use_reloader=use_reloader)

if __name__ == '__main__':
    main()
