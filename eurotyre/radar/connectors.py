"""Quatre connecteurs indépendants vers des flux autorisés. Aucun scraper de sites marchands."""
from datetime import datetime, timezone
from io import BytesIO
import ipaddress
import socket
from urllib.parse import urlsplit
from ..imports import read_upload
from . import RETAILERS
from .prices import timestamp


class DisabledConnector:
    def __init__(self, name, reason='Aucun flux autorisé configuré'):
        self.name, self.reason = name, reason

    def fetch(self, products, settings):
        raise PermissionError(self.reason)


class FileConnector:
    def __init__(self, name, rows, authorization, simulated=False):
        self.name, self.rows = name, rows
        self.authorization, self.simulated = authorization, simulated

    def fetch(self, products, settings):
        if not self.authorization:
            raise PermissionError('La provenance autorisée du fichier doit être confirmée.')
        if not 1 <= len(self.rows) <= 10000:
            raise ValueError('De 1 à 10 000 lignes attendues.')
        return [dict(row, simulated=self.simulated, authorization=self.authorization) for row in self.rows]


def public_https(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('Le flux doit utiliser une URL HTTPS sans identifiants intégrés.')
    if parsed.hostname.lower() == 'localhost':
        raise ValueError('Adresse de flux non publique.')
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except OSError as e:
        raise ValueError('Nom du flux inaccessible.') from e
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError('Adresse de flux non publique.')
    return parsed


class AuthorizedFeedConnector:
    def __init__(self, name, config, session=None):
        self.name, self.config, self.session = name, config, session

    def fetch(self, products, settings):
        config = self.config
        proof = str(config.get('authorization_reference', '')).strip()
        if config.get('approved') is not True or not proof or not config.get('approved_by'):
            raise PermissionError('Autorisation documentée manquante')
        try:
            if timestamp(config.get('approved_until')) <= datetime.now(timezone.utc):
                raise PermissionError('Autorisation expirée')
        except (ValueError, TypeError) as e:
            raise PermissionError('Date de validité de l’autorisation manquante') from e
        url = str(config.get('url', ''))
        parsed = public_https(url)
        allowed_hosts = config.get('allowed_hosts', [])
        if parsed.hostname not in allowed_hosts:
            raise PermissionError('Le domaine du flux ne figure pas dans l’autorisation configurée')
        import requests
        session = self.session or requests.Session()
        headers = {'User-Agent': config.get('user_agent') or 'Eurotyre-Market-Price-Radar/1.0'}
        if config.get('token'):
            headers['Authorization'] = 'Bearer ' + str(config['token'])
        try:
            with session.get(url, headers=headers, timeout=(5, 30), allow_redirects=False, stream=True) as response:
                if response.status_code in (401, 403, 429) or 300 <= response.status_code < 400:
                    raise PermissionError('Accès refusé, limité ou redirigé ; aucune tentative de contournement')
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_content(65536):
                    body.extend(chunk)
                    if len(body) > 5 * 1024 * 1024:
                        raise ValueError('Flux limité à 5 Mo')
                kind = config.get('format', 'json')
                if kind == 'json':
                    import json
                    data = json.loads(body)
                    rows = data.get('observations') if isinstance(data, dict) else data
                elif kind == 'csv':
                    frame, _ = read_upload(bytes(body), 'flux.csv')
                    rows = frame.to_dict('records')
                else:
                    raise ValueError('Formats de flux acceptés : json ou csv')
        except requests.RequestException as e:
            # Ne pas exposer l'URL ni le jeton dans les rapports/écrans/logs.
            raise ValueError('Le flux autorisé est indisponible') from e
        if not isinstance(rows, list) or not 1 <= len(rows) <= 10000 or any(not isinstance(r, dict) for r in rows):
            raise ValueError('Le flux doit contenir de 1 à 10 000 observations structurées')
        return [dict(row, authorization=proof, simulated=False) for row in rows]


def configured_connectors(configs):
    return [AuthorizedFeedConnector(name, configs[name]) if configs.get(name) else DisabledConnector(name)
            for name in RETAILERS]
