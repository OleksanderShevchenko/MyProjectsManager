import datetime
import gzip
import logging
import os
import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger('work_time_reporter')


class Command(BaseCommand):
    help = "Creates an automated database backup (PostgreSQL pg_dump or SQLite dump) with optional gzip compression and rotation."

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            type=str,
            default=str(settings.BASE_DIR / 'db_backups'),
            help='Directory path where backup files will be saved (default: db_backups/)',
        )
        parser.add_argument(
            '--keep',
            type=int,
            default=10,
            help='Number of most recent backup files to keep (older backups will be pruned). Set to 0 to disable pruning.',
        )
        parser.add_argument(
            '--no-compress',
            action='store_true',
            default=False,
            help='Do not compress the backup with gzip.',
        )

    def handle(self, *args, **options):
        output_dir = Path(options['output_dir'])
        output_dir.mkdir(parents=True, exist_ok=True)
        keep = options['keep']
        compress = not options['no_compress']

        db_config = settings.DATABASES['default']
        engine = db_config.get('ENGINE', '')
        raw_name = str(db_config.get('NAME') or 'database')
        dbname = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in Path(raw_name).stem)

        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        ext = 'sql.gz' if compress else 'sql'
        filename = f"backup_{dbname}_{timestamp}.{ext}"
        filepath = output_dir / filename

        self.stdout.write(f"Initiating database backup for '{dbname}' ({engine})...")

        if 'postgresql' in engine:
            self._backup_postgresql(db_config, filepath, compress)
        elif 'sqlite3' in engine:
            self._backup_sqlite(db_config, filepath, compress)
        else:
            raise CommandError(f"Unsupported database engine for automated backup: {engine}")

        file_size_kb = filepath.stat().st_size / 1024
        msg = f"Database backup successfully created: {filepath} ({file_size_kb:.1f} KB)"
        self.stdout.write(self.style.SUCCESS(msg))
        logger.info(msg)

        if keep > 0:
            self._prune_old_backups(output_dir, keep)

    def _backup_postgresql(self, db_config, filepath, compress):
        dbname = db_config.get('NAME')
        user = db_config.get('USER')
        password = db_config.get('PASSWORD')
        host = db_config.get('HOST')
        port = db_config.get('PORT')

        cmd = ['pg_dump']
        if host:
            cmd.extend(['-h', str(host)])
        if port:
            cmd.extend(['-p', str(port)])
        if user:
            cmd.extend(['-U', str(user)])
        cmd.extend(['--no-owner', '--no-privileges', str(dbname)])

        env = os.environ.copy()
        if password:
            env['PGPASSWORD'] = str(password)

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )

            if compress:
                with gzip.open(filepath, 'wb') as gz_file:
                    shutil.copyfileobj(process.stdout, gz_file)
            else:
                with open(filepath, 'wb') as sql_file:
                    shutil.copyfileobj(process.stdout, sql_file)

            _, stderr = process.communicate()
            if process.returncode != 0:
                if filepath.exists():
                    filepath.unlink()
                err_msg = stderr.decode('utf-8', errors='replace').strip()
                raise CommandError(f"pg_dump failed (exit code {process.returncode}): {err_msg}")

        except FileNotFoundError:
            raise CommandError("pg_dump executable not found. Please ensure PostgreSQL client tools are installed.")

    def _backup_sqlite(self, db_config, filepath, compress):
        sqlite_file = Path(db_config.get('NAME'))
        if not sqlite_file.exists():
            raise CommandError(f"SQLite database file not found at: {sqlite_file}")

        if compress:
            with open(sqlite_file, 'rb') as f_in, gzip.open(filepath, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        else:
            shutil.copyfile(sqlite_file, filepath)

    def _prune_old_backups(self, output_dir: Path, keep: int):
        backup_files = sorted(
            [f for f in output_dir.glob("backup_*") if f.is_file()],
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )

        if len(backup_files) > keep:
            to_remove = backup_files[keep:]
            for old_file in to_remove:
                try:
                    old_file.unlink()
                    self.stdout.write(f"Pruned old backup: {old_file.name}")
                    logger.info(f"Pruned old database backup: {old_file.name}")
                except OSError as e:
                    self.stdout.write(self.style.WARNING(f"Could not remove old backup {old_file.name}: {e}"))
