# velib_rx


Two points worth mentionning:

There is no difference between sending PropertiesChanged and 'exporting' a property.
These two concepts have been merged in `publish_ve_property`. 
When called it sends PropertiesChanged and caches the property. 
When an other service asks for it, it will automatically serve the cached data.
It also takes care of "TreeExport".

You don't have to monitor NameOwnerChanged. velib_rx will do that for you. 
Just call `observe_ve_property` with the service_name/object_path you are instereted in and 
velib_rx will do the necessary to serve it to you efficiently. (You can use '*' wildcards 
at the end of both parameters)