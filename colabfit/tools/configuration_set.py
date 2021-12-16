from hashlib import sha512

from colabfit import HASH_SHIFT


class ConfigurationSet:
    """
    A configuration set defines a group of configurations and aggregates
    information about those configurations to improve queries.

    Note that a configuration set should only be constructed by loading from an
    existing database (in order to aggregate the info)

    Attributes:

        configuration_ids (list):
            A list of all attached configuration IDs

        description (str):
            A human-readable description of the configuration set

        aggregated_info (dict):
            A dictionary of information that was aggregated from all of the
            attached configurations. Contains the following information:

                * nconfigurations: the total number of configurations
                * nsites: the total number of sites
                * nelements: the total number of unique element types
                * elements: the element types
                * individual_elements_ratios: a set of elements ratios generated
                by looping over each configuration, extracting its concentration of
                each element, and adding the tuple of concentrations to the set
                * total_elements_ratios: the ratio of the total count of atoms
                    of each element type over nsites
                * labels: the union of all configuration labels
                * labels_counts: the total count of each label
                * chemical_formula_reduced: the set of all reduced chemical
                    formulae
                * chemical_formula_anonymous: the set of all anonymous chemical
                    formulae
                * chemical_formula_hill: the set of all hill chemical formulae
                * nperiodic_dimensions: the set of all numbers of periodic
                    dimensions
                * dimension_types: the set of all periodic boundary choices
    """

    def __init__(self, configuration_ids, description, aggregated_info):
        self.configuration_ids  = configuration_ids
        self.description        = description
        self.aggregated_info    = aggregated_info


    def __hash__(self):

        cs_hash = sha512()
        for i in sorted(self.configuration_ids):
            cs_hash.update(str(i).encode('utf-8'))

        return int(cs_hash.hexdigest()[:16], 16)-HASH_SHIFT