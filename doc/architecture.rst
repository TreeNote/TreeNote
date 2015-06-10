Architecture
============


The application uses two data structures: The persistent CouchDB database and a pile of connected ``Tree_item`` instances, which are created from the database each time the application opens. If the user or a distant participant does an edit, the shared database is edited. This database change is detected and reflected to the local ``Tree_item`` instances.

The ``QTreeView`` interacts with the underlying data structure through the class ``TreeModel``, a subclass of the ``QAbstractItemModel``. The overwritten methods can be divided into two categories:

1. When the *views needs data* to build or change itself, it calls the following methods:

	* Each ``QModelIndex`` contains a pointer to a ``Tree_item``. It can be retrieved with ``getItem(index)``.
	* ``index(row, parent_index)`` and ``parent(index)`` return a specific ``QModelIndex``
	* ``rowCount(index)`` returns not just the row count of the ``Tree_item`` to the given ``index``, but calls ``Tree_item : init_childs`` to get the children from the database and insert them as new ``Tree_item`` objects into the local data instance.


2. When the *user does an action*, methods like ``insertRows(), removeRows(), move_left()`` and ``setData()`` are called. They edit the database. For example if a new ``Tree_item`` was added, we insert the id of the new item to the 'children' list of the parent database item and we append a dictionary like this to the change: ``{'method': 'added', 'position': 2, 'id_list': $[$'07242da3d8e552bb9301b23979000f56'$]$``.`` Nothing more is done, the view is not updated.

However, all changes to the databases are observed by the ``Updater`` thread. It reads what was done and edits the ``Tree_item`` instances accordingly. The view automatically updates itself to this edits.

When a changes comes in, the ``Updater`` thread needs the ``Tree_item`` object for the changed item. For this, a dictionary ``id_index_dict`` is used which stores references to ``QModelIndexes`` for given id's.