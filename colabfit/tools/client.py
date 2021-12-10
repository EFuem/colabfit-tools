import numpy as np
from getpass import getpass
# from montydb import MontyClient
from pymongo import MongoClient

from colabfit import (
    _CONFIGS_COLLECTION, _PROPS_COLLECTION, _PROPSETTINGS_COLLECTION,
    _CONFIGSETS_COLLECTION, _PROPDEFS_COLLECTION,
    ATOMS_NAME_FIELD, ATOMS_LABELS_FIELD, ATOMS_LAST_MODIFIED_FIELD
)
from colabfit.tools.database import Database
from colabfit.tools.configuration import process_species_list

# class DatabaseClient(MontyClient):
class DatabaseClient(MongoClient):
    """
    A DatabaseClient serves as an interface to the underlying HDF5 database, and
    provides additinal functionality like filtering and optimized queries.

    The DatabaseClient is a client to a Mongo/Monty database which stores
    pointers to the contents of the HDF5 database. This allows the data to be
    stored in an efficient format for I/O, while still providing the advanced
    querying functionality of a Mongo database.


    Brainstorming:

    * The Mongo database will need wrappers to all of the Database functions
        * insert_data
        * concatenate_group
    * In fact, shouldn't almost ALL of the Database functions be "hidden",
      except for maybe:
        * concatenate_group
        * get_data

    * The client should be able to "attach()" to multiple databases.
        * In which case all of the Client functions would need to take in an
        additional argument specifying _which_ database to operate on.

    * Maybe let's start off with just one database?
    * Because the Client should theoretically work on many databases, I think it
      makes the most sense that a user ONLY be expected to use the Client
      functions
        * So all of the Database functions SHOULD be wrapped


    Attributes:

        database (Database):
            The underlying HDF5 database
    """
    def __init__(self, database_path, mode='r', client_repo=None, **kwargs):
        """
        Args:

            database_path (str):
                The path to the database

            mode (str):
                'r', 'w', 'a', or 'w+'

            client_repo (str):
                A directory path for on-disk storage of the Mongo/Monty
                database, or the URI for an existing
                client, or None. If None, the Mongo/Monty database is stored
                entirely in memory.
        """
        # if client_repo is None:
        #     client_repo = ":memory:"

        # super().__init__(repository=client_repo, **kwargs)
        # user = input("mongodb username: ")
        # pwrd = getpass("mongodb password: ")
        user = 'colabfitAdmin'
        pwrd = 'Fo08w3K&VEY&'

        super().__init__(
            'mongodb://{}:{}@localhost:27017/'.format(user, pwrd)
        )
        self.configurations         = self.db[_CONFIGS_COLLECTION]
        self.properties             = self.db[_PROPS_COLLECTION]
        self.property_definitions   = self.db[_PROPDEFS_COLLECTION]
        self.property_settings      = self.db[_PROPSETTINGS_COLLECTION]
        self.configuration_sets     = self.db[_CONFIGSETS_COLLECTION]

        self.database = Database(name=database_path, mode=mode)


    def insert_data(
        self, configurations, property_map=None, property_settings=None,
        generator=False
        ):
        """
        A wrapper to Database.insert_data() which also adds important queryable
        metadata about the configurations into the Client's server.

        Note that when adding the data, the Mongo server will store the
        bi-directional relationships between the data. For example, a property
        will point to its configurations, but those configurations will also
        point back to any linked properties.

        Args:

            configurations (list or Configuration):
                The list of configurations to be added.

            property_map (dict):
                A dictionary that is used to specify how to load a defined
                property off of a configuration. Note that the top-level keys in
                the map must be the names of properties that have been
                previously defined using
                :meth:`~colabfit.tools.database.Database.add_property_definition`.

                If None, only loads the configuration information (atomic
                numbers, positions, lattice vectors, and periodic boundary
                conditions).

            property_settings (dict)
                key = property name (same as top-level keys in property_map).
                val = property settings ID that has been previously entered into
                the database using
                :meth:`~colabfit.tools.database.Database.insert_property_settings`

            generator (bool):
                If true, this function becomes a generator which only adds the
                configurations one at a time. This is useful if the
                configurations can't all fit in memory at the same time. Default
                is False.
        """

        # Tuples of (config_id, property_id) or (config_id, None)
        ids = self.database.insert_data(
            configurations=configurations,
            property_map=property_map,
            property_settings=property_settings,
            generator=generator
        )

        # TODO: this kind of defeats the purpose of a generator version

        co_ids, pr_ids = list(zip(*ids))

        # Add all of the configurations into the Mongo server
        for cid, config in zip(
            list(set(co_ids)),
            self.database.get_configurations(co_ids, generator=generator)
            ):

            atomic_symbols = config.get_chemical_symbols()
            processed_fields = process_species_list(atomic_symbols)

            # NOTE: when using update(), you can't have strings that start with
            # the same words (e.g., 'elements', and 'elements_ratios')
            # see here: https://stackoverflow.com/questions/50947772/updating-the-path-x-would-create-a-conflict-at-x

            # Add if doesn't exist, else update (since last-modified changed)
            self.configurations.update_one(
                {'_id': cid},  # filter
                {  # update
                    '$addToSet': {
                        'names': list(config.info[ATOMS_NAME_FIELD]),
                        'labels': list(config.info[ATOMS_LABELS_FIELD]),
                    },
                    '$setOnInsert': {
                        '_id': cid,
                        'last_modified': config.info[ATOMS_LAST_MODIFIED_FIELD],
                        'elements': processed_fields['elements'],
                        'nelements': processed_fields['nelements'],
                        'elements_ratios': processed_fields['elements_ratios'],
                        'chemical_formula_reduced': processed_fields['chemical_formula_reduced'],
                        'chemical_formula_anonymous': processed_fields['chemical_formula_anonymous'],
                        'chemical_formula_hill': config.get_chemical_formula(),
                        'natoms': len(config),
                        'dimension_types': config.get_pbc().astype(int),
                        'nperiodic_dimensions': sum(config.get_pbc()),
                        'lattice_vectors': np.array(config.get_cell()).tolist(),
                    }
                },
                upsert=True,  # overwrite if exists already
            )

        # Now add all of the properties
        for pid in list(set(pr_ids)):
            prop_type = self.database[f'properties/types/data/{pid}'][()]

            if prop_type in property_settings:
                labels = property_settings[prop_type].labels
            else:
                labels = set()
            # settings_id = self.database[f'properties/settings_ids/data/{pid}'][()]
            # settings = self.database.get_property_settings(settings_id)['settings']

            self.properties.update_one(
                {'_id': pid},
                {
                    '_id': pid,
                    'type': prop_type,
                    '$addToSet': {
                        'labels': labels,
                    },
                    'last_modified': self.database[f'properties/last_modified/{pid}'][()]
                },
                upsert=True
            )

        # Now update all of the relationships
        for cid, pid in zip(co_ids, pr_ids):

            self.configurations.update_one(
                {'_id': cid},
                {'$addToSet': {'relationships': pid}}
            )

            self.properties.update_one(
                {'_id': pid},
                {'$addToSet': {'relationships': cid}}
            )

        return ids

    
    def insert_property_definition(self, definition):
        """
        Inserts a new property definition into the database. Checks that
        definition is valid, then builds all necessary groups in
        :code:`/root/properties`.

        Args:

            definition (dict):
                The map defining the property. See the example below, or the
                `OpenKIM Properties Framework <https://openkim.org/doc/schema/properties-framework/>`_
                for more details.

        Example definition:

        ..code-block:: python

            property_definition = {
                'property-id': 'default',
                'property-title': 'A default property used for testing',
                'property-description': 'A description of the property',
                'energy': {'type': 'float', 'has-unit': True, 'extent': [], 'required': True, 'description': 'empty'},
                'stress': {'type': 'float', 'has-unit': True, 'extent': [6], 'required': True, 'description': 'empty'},
                'name': {'type': 'string', 'has-unit': False, 'extent': [], 'required': True, 'description': 'empty'},
                'nd-same-shape': {'type': 'float', 'has-unit': True, 'extent': [2,3,5], 'required': True, 'description': 'empty'},
                'nd-diff-shape': {'type': 'float', 'has-unit': True, 'extent': [":", ":", ":"], 'required': True, 'description': 'empty'},
                'forces': {'type': 'float', 'has-unit': True, 'extent': [":", 3], 'required': True, 'description': 'empty'},
                'nd-same-shape-arr': {'type': 'float', 'has-unit': True, 'extent': [':', 2, 3], 'required': True, 'description': 'empty'},
                'nd-diff-shape-arr': {'type': 'float', 'has-unit': True, 'extent': [':', ':', ':'], 'required': True, 'description': 'empty'},
            }
        """

        self.database.insert_property_definition(definition)

        self.property_definitions.update_one(
            {'_id': definition['property-id']},
            {
                '$setOnInsert': {
                    '_id': definition['property-id'],
                    'definition': definition
                }
            }
        )


    def insert_property_settings(self, pso_object):
        """
        Inserts a new property settings object into the database by creating
        and populating the necessary groups in :code:`/root/property_settings`.

        Args:

            pso_object (PropertySettings)
                The :class:`~colabfit.tools.property_settings.PropertySettings`
                object to insert into the database.


        Returns:

            pso_id (str):
                The ID of the inserted property settings object. Equals the hash
                of the object.
        """

        pso_id = self.database.insert_property_settings(pso_object)

        self.property_settings.update_one(
            {'_id': pso_id},
            {
                '$addToSet': {
                    'labels': list(pso_object.labels)
                },
                '$setOnInsert': {
                    '_id': pso_id,
                    'method': pso_object.method,
                    'description': pso_object.description,
                    'files': [
                        {
                            'file_name': ftup[0],
                            'file_contents': ftup[1],
                        } for ftup in pso_object.files
                    ],
                }
            }
        )

        return pso_id