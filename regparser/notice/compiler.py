import copy
import itertools
from regparser.tree.struct import Node, find
from regparser.utils import roman_nums

""" Notices indicate how a regulation has changed since the last version. This
module contains code to compile a regulation from a notice's changes. """

class RegulationTree(object):
    def __init__(self, previous_tree):
        self.tree = copy.deepcopy(previous_tree)

    def get_parent_label(self, node):
        if node.node_type == Node.SUBPART:
            return node.label[0]
        else:
            parent_label = node.label[:-1]
            return '-'.join(parent_label)

    def make_label_sortable(self, label, roman=False):
        """ Make labels sortable, but converting them as appropriate. 
        Also, appendices have labels that look like 30(a), we make those 
        appropriately sortable. """

        if label.isdigit():
            return (int(label),)
        if label.isalpha():
            if roman:
                romans = list(itertools.islice(roman_nums(), 0, 50))
                return 1 + romans.index(label)
            else:
                return (label,)
        else:
            m = re.match(r"([0-9]+)([\(])([a-z]+)([\)])", label, re.I)
            return (int(m.groups()[0]), m.groups()[2])

    def make_root_sortable(self, label, node_type):
        if node_type == Node.SUBPART or node_type == Node.EMPTYPART:
            return (0, label[-1])
        elif node_type == Node.APPENDIX:
            return (1, label[-1])
        elif node_type == Node.INTERP:
            return (2,)

    def add_to_root(self, node):
        self.tree.children.append(node)

        for c in self.tree.children:
            c.sortable = self.make_root_sortable(c.label, c.node_type)

        self.tree.children.sort(key=lambda x: x.sortable)
    
        for c in self.tree.children:
            del c.sortable

    def add_child(self, children, node):
        children.append(node)

        for c in children:
            c.sortable = self.make_label_sortable(
                c.label[-1], roman=(len(c.label) == 5))

        children.sort(key=lambda x: x.sortable)

        for c in children:
            del c.sortable
        return children

    def replace_node_and_subtree(self, node):
        """ Replace an existing node in the tree with node.  """
        #find parent of node
        parent_label = self.get_parent_label(node)
        parent = find(self.tree, parent_label) 

        other_children = [c for c in parent.children if c.label != node.label]
        parent.children = self.add_child(other_children, node)

    def add_node(self, node):
        """ Add an entirely new node to the regulation tree. """

        if node.node_type == Node.SUBPART:
            return self.add_to_root(node)

        parent_label = self.get_parent_label(node)
        parent = find(self.tree, parent_label)
        parent.children = self.add_child(parent.children, node)

    def add_section(self, node, subpart_label):
        subpart = find(self.tree, '-'.join(subpart_label))
        subpart.children = self.add_child(subpart.children, node)

    def replace_node_text(self, label, change):
        node = find(self.tree, label)
        node.text = change['node']['text']

    def get_subparts(self):
        """ Get all the subparts and empty parts in the tree.  """
        def subpart_type(c):
            return c.node_type in (Node.EMPTYPART, Node.SUBPART)

        return [c for c in self.tree.children if subpart_type(c)]

    def create_new_subpart(self, subpart_label):
        #XXX Subparts need titles. We'll need to pull this up from parsing.
        subpart_node = Node('', [], subpart_label, None, Node.SUBPART) 
        self.add_to_root(subpart_node)
        return subpart_node

    def get_subpart_for_node(self, label):
        subparts = self.get_subparts()
        subparts_with_label = [s for s in subparts if find(s, label) is not None]

        if len(subparts_with_label) > 0:
            return subparts_with_label[0]

    def move_to_subpart(self, label, subpart_label):
        
        destination = find(self.tree, '-'.join(subpart_label))

        if destination is None:
            destination = self.create_new_subpart(subpart_label)

        subpart_with_node = self.get_subpart_for_node(label)

        if destination and subpart_with_node:
            node = find(subpart_with_node, label)
            other_children = [c for c in subpart_with_node.children if c.label_id() != label]
            subpart_with_node.children = other_children
            destination.children = self.add_child(destination.children, node)

def dict_to_node(node_dict):
    """ Convert a dictionary representation of a node into a Node object if 
    it contains the minimum required field. Otherwise, pass it through 
    unchanged. """
    minimum_fields = set(('text', 'label', 'node_type'))
    if minimum_fields.issubset(node_dict.keys()):
        node = Node(
            node_dict['text'], [], node_dict['label'],
            node_dict.get('title', None), node_dict['node_type'])
        if 'tagged_text' in node_dict:
            node.tagged_text = node_dict['tagged_text']
        return node
    else:
        return node_dict

def sort_labels(labels):
    """ Deal with higher up elements first. """
    sorted_labels = sorted(labels, key=lambda x: len(x))

    #The length of a Subpart label doesn't indicate it's level in the tree
    subparts = [l for l in sorted_labels if 'Subpart' in l]
    non_subparts = [l for l in sorted_labels if 'Subpart' not in l]

    return subparts + non_subparts

def compile_regulation(previous_tree, notice_changes):
    reg = RegulationTree(previous_tree)

    labels = sort_labels(notice_changes.keys())

    for label in labels:
        changes = notice_changes[label]
        for change in changes:
            replace_subtree = 'field' not in change

            if change['action'] == 'PUT' and replace_subtree:
                node = dict_to_node(change['node'])
                reg.replace_node_and_subtree(node)
            elif change['action'] == 'PUT' and change['field'] == '[text]':
                reg.replace_node_text(label, change)
            elif change['action'] == 'POST':
                node = dict_to_node(change['node'])
                if 'subpart' in change and len(node.label) == 2:
                    reg.add_section(node, change['subpart'])
                else:
                    reg.add_node(node)
            elif change['action'] == 'DESIGNATE':
                if 'Subpart' in change['destination']:
                    reg.move_to_subpart(label, change['destination'])
            else:
                print "%s: %s" % (change['action'], label)
    return reg
