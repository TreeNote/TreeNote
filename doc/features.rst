Features
============


Search
------
Filtering is done with the ``QSortFilterProxyModel`` very easily. It is inserted between the regular model and the view and passes through only the desired items, for example the ones which match to a search string.


Crashes
-------
The application crashed occasionally after deleting an item. As stated earlier, ``index(row)`` is called almost constantly by the view to refresh itself. That method calls ``getItem(index)`` which gets a ``Tree_item`` with the help of a pointer. When a ``Tree_item`` is deleted, the garbage collector frees the used memory. Now, sometimes ``index(row)`` is called and the pointer accesses a location in memory of a deleted ``Tree_item``. If that location is used by something else, the application crashes.

To prevent this behavior, all valid pointers to ``Tree_items`` are stored in a ``pointer_set``. Before ``index(row)`` uses a pointer, it checks if it is valid. If a ``Tree_item`` is deleted, the corresponding pointer gets removed from the set.

There is another exception when there are many changes in a short period of time. This is because incoming changes are sometimes out of order. This is not fixed yet.