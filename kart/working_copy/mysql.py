import contextlib
import logging
import time


from sqlalchemy.dialects.mysql.base import MySQLIdentifierPreparer
from sqlalchemy.sql.functions import Function
from sqlalchemy.orm import sessionmaker
from sqlalchemy.types import UserDefinedType

from . import mysql_adapter
from .db_server import DatabaseServer_WorkingCopy
from .table_defs import MySqlKartTables
from kart import crs_util
from kart.geometry import Geometry
from kart.sqlalchemy import text_with_inlined_params
from kart.sqlalchemy.create_engine import mysql_engine


class WorkingCopy_MySql(DatabaseServer_WorkingCopy):
    """
    MySQL working copy implementation.
    Unlike other database-servers (eg Postgresql, Microsoft SQL Server) - MySQL has no concept of a schema (where
    "schema" means a type of namespace, that exists within a database, that exists within a database server / cluster).
    So typically, a Kart manages a working copy by managing every table inside an entire db schema, ie:
    >>> postgresql://HOST[:PORT]/DBNAME/DBSCHEMA
    But in the case of a MySQL working copy, where schemas don't exist, Kart manages a working copy by managing
    every table inside entire database:
    >>> mysql://HOST[:PORT]/DBNAME

    Note that, for compatibility with other working copy implementations, self.db_schema (and escaped variant
    self.DB_SCHEMA) actually contain the database name in this implementation.

    Requirements:
    1. The MySQL server needs to exist
    2. The database user needs to be able to:
        - Create the specified database (unless it already exists).
        - Create, delete and alter tables and triggers in the specified database.
    """

    WORKING_COPY_TYPE_NAME = "MySQL"
    URI_SCHEME = "mysql"

    URI_FORMAT = "//HOST[:PORT]/DBNAME"
    URI_VALID_PATH_LENGTHS = (1,)
    INVALID_PATH_MESSAGE = "URI path must have one part - the database name"

    def __init__(self, repo, location):
        """
        uri: connection string of the form mysql://[user[:password]@][netloc][:port][/dbname][?param1=value1&...]
        """
        self.L = logging.getLogger(self.__class__.__qualname__)

        self.repo = repo
        self.uri = self.location = location

        self.check_valid_db_uri(self.uri, repo)
        self.db_uri, self.db_schema = self._separate_db_schema(
            self.uri, expected_path_length=1
        )

        self.engine = mysql_engine(self.db_uri)
        self.sessionmaker = sessionmaker(bind=self.engine)
        self.preparer = MySQLIdentifierPreparer(self.engine.dialect)

        self.kart_tables = MySqlKartTables(self.db_schema)

    def _create_table_for_dataset(self, sess, dataset):
        table_spec = mysql_adapter.v2_schema_to_mysql_spec(dataset.schema, dataset)
        sess.execute(
            f"""CREATE TABLE IF NOT EXISTS {self.table_identifier(dataset)} ({table_spec});"""
        )
        sess.execute(
            f"ALTER TABLE {self.table_identifier(dataset)} COMMENT = :comment",
            {"comment": dataset.get_meta_item("title")},
        )

    def _type_def_for_column_schema(self, col, dataset=None):
        if col.data_type == "geometry":
            crs_name = col.extra_type_info.get("geometryCRS")
            crs_id = None
            if dataset is not None:
                crs_id = (
                    crs_util.get_identifier_int_from_dataset(dataset, crs_name) or 0
                )
            # This user-defined GeometryType adapts Kart's GPKG geometry to SQL Server's native geometry type.
            return GeometryType(crs_id)
        elif col.data_type == "timestamp":
            return TimestampType
        else:
            # Don't need to specify type information for other columns at present, since we just pass through the values.
            return None

    def _is_dataset_supported(self, dataset):
        return not any(
            self._is_unsupported_geometry_column(col)
            for col in dataset.schema.geometry_columns
        )

    def _is_unsupported_geometry_column(self, col):
        geometry_type = col.extra_type_info.get("geometryType", "geometry")
        return len(geometry_type.strip().split(" ")) > 1

    def _write_meta(self, sess, dataset):
        # The only metadata to write that is stored outside the table is custom CRS.
        for crs in mysql_adapter.generate_mysql_spatial_ref_sys(dataset):
            existing_crs = sess.execute(
                """
                SELECT organization, definition FROM information_schema.st_spatial_reference_systems
                WHERE srs_id = :srs_id;
                """,
                crs,
            ).fetchone()

            if existing_crs:
                # Don't overwrite existing CRS definitions if they are built-ins. Doing so is an error in MYSQL:
                if existing_crs['ORGANIZATION'] == "EPSG":
                    continue
                # Don't try to replace a CRS if a matching one already exists - overwriting a CRS with an identical
                # CRS is a no-op, but one which requires certain permissions, so we avoid it if we can.
                if existing_crs['DEFINITION'] == crs['definition']:
                    continue
                # Don't replace a CRS definition if it is currently being referenced. Doing so is an error in MySQL.
                if sess.scalar(
                    "SELECT COUNT(*) FROM information_schema.st_geometry_columns WHERE srs_id = :srs_id;",
                    crs,
                ):
                    continue

            sess.execute(
                """
                CREATE OR REPLACE SPATIAL REFERENCE SYSTEM :srs_id
                ORGANIZATION :organization IDENTIFIED BY :org_id
                NAME :name DEFINITION :definition;
                """,
                crs,
            )

    def _delete_meta(self, sess, dataset):
        # The only metadata outside the table itself is CRS definitions. We don't delete them however, for 2 reasons:
        # 1. CRS definitions have global scope and we can't tell if we created them. Even if they're not being used
        # right now, somebody else might have created them and expect them to stay where they are until they are needed.
        # 2. We might need that CRS definition again in a minute (eg next time we switch branch) and we might lack
        # permissions to create or delete CRS definitions. Better to just leave things as-is.
        pass

    def _create_spatial_index_post(self, sess, dataset):
        # Only implemented as _create_spatial_index_post:
        # It is more efficient to write the features first, then index them all in bulk.

        # TODO - MYSQL-PART-2 - We can only create a spatial index if the geometry column is declared
        # not-null, but a datasets V2 schema doesn't distinguish between NULL and NOT NULL columns.
        # So we don't know if the user would rather have an index, or be able to store NULL values.
        return  # Find a fix.

        L = logging.getLogger(f"{self.__class__.__qualname__}._create_spatial_index")

        geom_col = dataset.geom_column_name

        L.debug("Creating spatial index for %s.%s", dataset.table_name, geom_col)
        t0 = time.monotonic()

        sess.execute(
            f"ALTER TABLE {self.table_identifier(dataset)} ADD SPATIAL INDEX({self.quote(geom_col)})"
        )

        L.info("Created spatial index in %ss", time.monotonic() - t0)

    def _drop_spatial_index(self, sess, dataset):
        # MySQL deletes the spatial index automatically when the table is deleted.
        pass

    def _sno_tracking_name(self, trigger_type, dataset=None):
        """Returns the sno-branded name of the trigger reponsible for populating the sno_track table."""
        assert dataset is None
        return f"_sno_track_{trigger_type}"

    def _create_triggers(self, sess, dataset):
        table_identifier = self.table_identifier(dataset)
        pk_column = self.quote(dataset.primary_key)

        sess.execute(
            text_with_inlined_params(
                f"""
                CREATE TRIGGER {self._quoted_tracking_name('ins', dataset)}
                    AFTER INSERT ON {table_identifier}
                FOR EACH ROW
                    REPLACE INTO {self.KART_TRACK} (table_name, pk)
                    VALUES (:table_name, NEW.{pk_column})
                """,
                {"table_name": dataset.table_name},
            )
        )
        sess.execute(
            text_with_inlined_params(
                f"""
                CREATE TRIGGER {self._quoted_tracking_name('upd', dataset)}
                    AFTER UPDATE ON {table_identifier}
                FOR EACH ROW
                    REPLACE INTO {self.KART_TRACK} (table_name, pk)
                    VALUES (:table_name1, OLD.{pk_column}), (:table_name2, NEW.{pk_column})
                """,
                {"table_name1": dataset.table_name, "table_name2": dataset.table_name},
            )
        )
        sess.execute(
            text_with_inlined_params(
                f"""
                CREATE TRIGGER {self._quoted_tracking_name('del', dataset)}
                    AFTER DELETE ON {table_identifier}
                FOR EACH ROW
                    REPLACE INTO {self.KART_TRACK} (table_name, pk)
                    VALUES (:table_name, OLD.{pk_column})
                """,
                {"table_name": dataset.table_name},
            )
        )

    def _drop_triggers(self, sess, dataset):
        sess.execute(f"DROP TRIGGER {self._quoted_tracking_name('ins', dataset)}")
        sess.execute(f"DROP TRIGGER {self._quoted_tracking_name('upd', dataset)}")
        sess.execute(f"DROP TRIGGER {self._quoted_tracking_name('del', dataset)}")

    @contextlib.contextmanager
    def _suspend_triggers(self, sess, dataset):
        self._drop_triggers(sess, dataset)
        yield
        self._create_triggers(sess, dataset)

    def meta_items(self, dataset):
        with self.session() as sess:
            title = sess.scalar(
                """
                SELECT table_comment FROM information_schema.tables
                WHERE table_schema=:table_schema AND table_name=:table_name;
                """,
                {"table_schema": self.db_schema, "table_name": dataset.table_name},
            )
            yield "title", title

            table_info_sql = """
                SELECT
                    C.column_name, C.ordinal_position, C.data_type, C.srs_id,
                    C.character_maximum_length, C.numeric_precision, C.numeric_scale,
                    KCU.ordinal_position AS pk_ordinal_position
                FROM information_schema.columns C
                LEFT OUTER JOIN information_schema.key_column_usage KCU
                ON (KCU.table_schema = C.table_schema)
                AND (KCU.table_name = C.table_name)
                AND (KCU.column_name = C.column_name)
                WHERE C.table_schema=:table_schema AND C.table_name=:table_name
                ORDER BY C.ordinal_position;
            """
            r = sess.execute(
                table_info_sql,
                {"table_schema": self.db_schema, "table_name": dataset.table_name},
            )
            mysql_table_info = list(r)

            spatial_ref_sys_sql = """
                SELECT SRS.* FROM information_schema.st_spatial_reference_systems SRS
                LEFT OUTER JOIN information_schema.st_geometry_columns GC ON (GC.srs_id = SRS.srs_id)
                WHERE GC.table_schema=:table_schema AND GC.table_name=:table_name;
            """
            r = sess.execute(
                spatial_ref_sys_sql,
                {"table_schema": self.db_schema, "table_name": dataset.table_name},
            )
            mysql_spatial_ref_sys = list(r)

            id_salt = f"{self.db_schema} {dataset.table_name} {self.get_db_tree()}"
            schema = mysql_adapter.sqlserver_to_v2_schema(
                mysql_table_info, mysql_spatial_ref_sys, id_salt
            )
            yield "schema.json", schema.to_column_dicts()

            for crs_info in mysql_spatial_ref_sys:
                wkt = crs_info["DEFINITION"]
                id_str = crs_util.get_identifier_str(wkt)
                yield f"crs/{id_str}.wkt", crs_util.normalise_wkt(wkt)

    @classmethod
    def try_align_schema_col(cls, old_col_dict, new_col_dict):
        old_type = old_col_dict["dataType"]
        new_type = new_col_dict["dataType"]

        # Some types have to be approximated as other types in MySQL
        if mysql_adapter.APPROXIMATED_TYPES.get(old_type) == new_type:
            new_col_dict["dataType"] = new_type = old_type
            for key in mysql_adapter.APPROXIMATED_TYPES_EXTRA_TYPE_INFO:
                new_col_dict[key] = old_col_dict.get(key)

        return new_type == old_type

    _UNSUPPORTED_META_ITEMS = (
        "description",
        "metadata/dataset.json",
        "metadata.xml",
    )

    def _remove_hidden_meta_diffs(self, dataset, ds_meta_items, wc_meta_items):
        super()._remove_hidden_meta_diffs(dataset, ds_meta_items, wc_meta_items)

        # Nowhere to put these in SQL Server WC
        for key in self._UNSUPPORTED_META_ITEMS:
            if key in ds_meta_items:
                del ds_meta_items[key]

        for key in ds_meta_items.keys() & wc_meta_items.keys():
            if not key.startswith("crs/"):
                continue
            old_crs = crs_util.mysql_compliant_wkt(ds_meta_items[key])
            new_crs = crs_util.mysql_compliant_wkt(wc_meta_items[key])
            if old_crs == new_crs:
                # Hide any diff caused by making the CRS MySQL compliant.
                del ds_meta_items[key]
                del wc_meta_items[key]

    def _is_builtin_crs(self, crs):
        auth_name, auth_code = crs_util.parse_authority(crs)
        return auth_name == "EPSG"

    def _is_meta_update_supported(self, meta_diff):
        """
        Returns True if the given meta-diff is supported *without* dropping and rewriting the table.
        (Any meta change is supported if we drop and rewrite the table, but of course it is less efficient).
        meta_diff - DeltaDiff object containing the meta changes.
        """
        # For now, just always drop and rewrite.
        return not meta_diff


class GeometryType(UserDefinedType):
    """UserDefinedType so that V2 geometry is adapted to MySQL binary format."""

    # In Kart, all geometries are stored as WKB with axis-order=long-lat - since this is the GPKG
    # standard, and a Kart geometry is a normalised GPKG geometry. MySQL has to be explicitly told
    # that this is the ordering we use in WKB, since MySQL would otherwise expect lat-long ordering
    # as specified by ISO 19128:2005.
    AXIS_ORDER = "axis-order=long-lat"

    def __init__(self, crs_id):
        self.crs_id = crs_id

    def bind_processor(self, dialect):
        # 1. Writing - Python layer - convert Kart geometry to WKB
        return lambda geom: geom.to_wkb()

    def bind_expression(self, bindvalue):
        # 2. Writing - SQL layer - wrap in call to ST_GeomFromWKB to convert WKB to MySQL binary.
        return Function(
            "ST_GeomFromWKB", bindvalue, self.crs_id, self.AXIS_ORDER, type_=self
        )

    def column_expression(self, col):
        # 3. Reading - SQL layer - wrap in call to ST_AsBinary() to convert MySQL binary to WKB.
        return Function("ST_AsBinary", col, self.AXIS_ORDER, type_=self)

    def result_processor(self, dialect, coltype):
        # 4. Reading - Python layer - convert WKB to Kart geometry.
        return lambda wkb: Geometry.from_wkb(wkb)


class DateType(UserDefinedType):
    # UserDefinedType to read Dates as text. They are stored in MySQL as Dates but we read them back as text.
    def column_expression(self, col):
        # Reading - SQL layer - convert date to string in ISO8601.
        # https://dev.mysql.com/doc/refman/8.0/en/date-and-time-functions.html
        return Function("DATE_FORMAT", col, "%Y-%m-%d", type_=self)


class TimeType(UserDefinedType):
    # UserDefinedType to read Times as text. They are stored in MySQL as Times but we read them back as text.
    def column_expression(self, col):
        # Reading - SQL layer - convert timestamp to string in ISO8601.
        # https://dev.mysql.com/doc/refman/8.0/en/date-and-time-functions.html
        return Function("DATE_FORMAT", col, "%H:%i:%S", type_=self)


class TimestampType(UserDefinedType):
    """
    UserDefinedType to read Timestamps as text. They are stored in MySQL as Timestamps but we read them back as text.
    """

    def bind_processor(self, dialect):
        # 1. Writing - Python layer - remove timezone specifier - MySQL can't read timezone specifiers.
        # MySQL requires instead that the timezone is set in the database session (see create_engine.py)
        return lambda timestamp: timestamp.rstrip("Z")

    def column_expression(self, col):
        # 2. Reading - SQL layer - convert timestamp to string in ISO8601 with Z as the timezone specifier.
        # https://dev.mysql.com/doc/refman/8.0/en/date-and-time-functions.html
        return Function("DATE_FORMAT", col, "%Y-%m-%dT%H:%i:%SZ", type_=self)
