"""Strict YAML mapping loader without JSON-schema runtime dependencies."""
import yaml
from .errors import ValidationError

class StrictLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            if key in result:
                raise ValidationError(f'duplicate YAML key: {key}')
            result[key] = loader.construct_object(value_node, deep=deep)
        except TypeError as exc:
            raise ValidationError('YAML mapping keys must be scalar') from exc
    return result


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)
