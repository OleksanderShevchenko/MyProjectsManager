import gzip
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


@pytest.mark.django_db
class TestBackupDbCommand:
    def test_backup_sqlite_success(self, tmp_path, settings):
        """Test SQLite backup creation and compression."""
        mock_db = tmp_path / "test.db"
        mock_db.write_bytes(b"SQLITE_TEST_CONTENT")

        settings.DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': str(mock_db),
            }
        }

        out_dir = tmp_path / "backups"
        call_command('backup_db', output_dir=str(out_dir))

        files = list(out_dir.glob("*.sql.gz"))
        assert len(files) == 1
        with gzip.open(files[0], 'rb') as gz:
            assert gz.read() == b"SQLITE_TEST_CONTENT"

    def test_backup_sqlite_no_compress(self, tmp_path, settings):
        """Test SQLite backup without compression."""
        mock_db = tmp_path / "test.db"
        mock_db.write_bytes(b"UNCOMPRESSED_CONTENT")

        settings.DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': str(mock_db),
            }
        }

        out_dir = tmp_path / "backups"
        call_command('backup_db', output_dir=str(out_dir), no_compress=True)

        files = list(out_dir.glob("*.sql"))
        assert len(files) == 1
        assert files[0].read_bytes() == b"UNCOMPRESSED_CONTENT"

    @patch('subprocess.Popen')
    def test_backup_postgresql_success(self, mock_popen, tmp_path, settings):
        """Test PostgreSQL backup calls pg_dump and writes compressed output."""
        mock_process = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stdout.read = MagicMock(side_effect=[b"PG_DUMP_OUTPUT", b""])
        mock_process.communicate.return_value = (b"", b"")
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        settings.DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': 'test_pg_db',
                'USER': 'postgres',
                'PASSWORD': 'secret',
                'HOST': 'localhost',
                'PORT': '5432',
            }
        }

        out_dir = tmp_path / "backups"
        call_command('backup_db', output_dir=str(out_dir))

        files = list(out_dir.glob("*.sql.gz"))
        assert len(files) == 1
        mock_popen.assert_called_once()
        cmd_args = mock_popen.call_args[0][0]
        assert cmd_args[0] == 'pg_dump'
        assert '-h' in cmd_args
        assert 'test_pg_db' in cmd_args

    def test_backup_pruning(self, tmp_path, settings):
        """Test that old backup files are pruned when count exceeds keep argument."""
        out_dir = tmp_path / "backups"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Create 5 dummy backup files
        for i in range(5):
            f = out_dir / f"backup_db_2026010{i}_000000.sql.gz"
            f.write_bytes(b"content")

        mock_db = tmp_path / "test.db"
        mock_db.write_bytes(b"DB_DATA")

        settings.DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': str(mock_db),
            }
        }

        # Keep only 3
        call_command('backup_db', output_dir=str(out_dir), keep=3)

        files = list(out_dir.glob("backup_*"))
        assert len(files) == 3

    def test_backup_unsupported_engine(self, tmp_path, settings):
        """Test error raised when database engine is unsupported."""
        settings.DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.mysql',
                'NAME': 'mysql_db',
            }
        }
        with pytest.raises(CommandError, match="Unsupported database engine"):
            call_command('backup_db', output_dir=str(tmp_path))
