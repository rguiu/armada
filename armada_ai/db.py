"""Database persistence — re-exports from infrastructure.database for backward compatibility."""
from . import constants
from .infrastructure import database as _db

# Re-export all public symbols
init_db = _db.init_db
close_connection = _db.close_connection
add_project_label = _db.add_project_label
delete_project_label = _db.delete_project_label
list_project_labels = _db.list_project_labels
get_project_label_path = _db.get_project_label_path
create_node = _db.create_node
kill_node = _db.kill_node
hide_node = _db.hide_node
reparent_node = _db.reparent_node
rename_node = _db.rename_node
update_node_status = _db.update_node_status
add_status_report = _db.add_status_report
prune_all_old_reports = _db.prune_all_old_reports
vacuum_db = _db.vacuum_db
accumulate_cost = _db.accumulate_cost
increment_log_count = _db.increment_log_count
get_node = _db.get_node
get_node_by_name = _db.get_node_by_name
get_node_children = _db.get_node_children
get_all_nodes = _db.get_all_nodes
get_root_nodes = _db.get_root_nodes
get_nodes_by_project_label_id = _db.get_nodes_by_project_label_id
get_killed_nodes = _db.get_killed_nodes
get_node_reports = _db.get_node_reports
build_tree = _db.build_tree
existing_names = _db.existing_names
active_colours = _db.active_colours
recover_nodes = _db.recover_nodes
recover_live_nodes = _db.recover_live_nodes
get_restart_count_for_name = _db.get_restart_count_for_name
increment_restart_count = _db.increment_restart_count
snapshot_stats = _db.snapshot_stats
get_hourly_stats = _db.get_hourly_stats
get_stats_summary = _db.get_stats_summary
scan_builtin_extensions = _db.scan_builtin_extensions
list_extensions = _db.list_extensions
install_extension = _db.install_extension
remove_extension_assignment = _db.remove_extension_assignment
get_project_extensions = _db.get_project_extensions
_sync_projects_from_json = _db._sync_projects_from_json


def __getattr__(name: str):
    """Forward attribute access to constants for DB_PATH/DB_DIR/PROJECTS_FILE."""
    if name in ("DB_PATH", "DB_DIR", "PROJECTS_FILE"):
        return getattr(constants, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __setattr__(name: str, value):
    """Forward attribute sets to constants for DB_PATH/DB_DIR/PROJECTS_FILE."""
    if name in ("DB_PATH", "DB_DIR", "PROJECTS_FILE"):
        object.__setattr__(constants, name, value)
    else:
        object.__setattr__(__import__(__name__), name, value)
