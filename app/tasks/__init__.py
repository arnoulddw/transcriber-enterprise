# app/tasks/__init__.py
# This file makes the 'tasks' directory a Python package.

# It could potentially be used to coordinate the startup of multiple background tasks
# if more were added in the future. For now, it just marks the directory as a package.

# Example (if coordinating multiple tasks):
# import threading
# from . import cleanup
# from . import another_task
#
# def start_all_background_tasks(app):
#     """Starts all defined background tasks in separate threads."""
#     cleanup_thread = threading.Thread(target=cleanup.run_cleanup_task, args=(app,), daemon=True)
#     another_thread = threading.Thread(target=another_task.run_task, args=(app,), daemon=True)
#
#     cleanup_thread.start()
#     another_thread.start()
#     # Log that tasks have started