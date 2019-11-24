# -*- coding: utf-8 -*-

"""Implementation of RESCAL."""

from typing import Optional, Union

import torch
from torch import nn

from ..base import BaseModule
from ...losses import Loss
from ...regularizers import LpRegularizer, Regularizer
from ...triples import TriplesFactory
from ...utils import resolve_device


__all__ = [
    'RESCAL',
]


class RESCAL(BaseModule):
    """An implementation of RESCAL from [nickel2011]_.

    This model represents relations as matrices and models interactions between latent features.

    .. seealso::

       - OpenKE `implementation of RESCAL <https://github.com/thunlp/OpenKE/blob/master/models/RESCAL.py>`_
    """

    hpo_default = dict(
        embedding_dim=dict(type=int, low=50, high=350, q=25),
        regularization_weight=dict(type=float, low=0.001, high=0.1, scale='log'),
    )

    def __init__(
        self,
        triples_factory: TriplesFactory,
        embedding_dim: int = 50,
        entity_embeddings: Optional[nn.Embedding] = None,
        relation_embeddings: Optional[nn.Embedding] = None,
        criterion: Optional[Loss] = None,
        preferred_device: Optional[str] = None,
        random_seed: Optional[int] = None,
        init: bool = True,
        regularizer: Union[None, str, Regularizer] = 'nickel2011',
    ) -> None:
        """Initialize the model."""
        if regularizer == 'nickel2011':
            # According to https://github.com/mnick/rescal.py/blob/master/examples/kinships.py a normalized weight of
            # 10 is used.
            regularizer = LpRegularizer(
                device=resolve_device(preferred_device),
                weight=10,
                p=2.,
                normalize=True,
            )

        super().__init__(
            triples_factory=triples_factory,
            embedding_dim=embedding_dim,
            entity_embeddings=entity_embeddings,
            criterion=criterion,
            preferred_device=preferred_device,
            random_seed=random_seed,
            regularizer=regularizer,
        )

        self.relation_embeddings = relation_embeddings

        # Finalize initialization
        self._init_weights_on_device()

    def init_empty_weights_(self):  # noqa: D102
        if self.entity_embeddings is None:
            self.entity_embeddings = nn.Embedding(self.num_entities, self.embedding_dim)
        if self.relation_embeddings is None:
            self.relation_embeddings = nn.Embedding(self.num_relations, self.embedding_dim ** 2)

        return self

    def clear_weights_(self):  # noqa: D102
        self.entity_embeddings = None
        self.relation_embeddings = None
        return self

    def score_hrt(self, hrt_batch: torch.LongTensor) -> torch.FloatTensor:  # noqa: D102
        # Get embeddings
        # shape: (b, d)
        h = self.entity_embeddings(hrt_batch[:, 0]).view(-1, 1, self.embedding_dim)
        # shape: (b, d, d)
        r = self.relation_embeddings(hrt_batch[:, 1]).view(-1, self.embedding_dim, self.embedding_dim)
        # shape: (b, d)
        t = self.entity_embeddings(hrt_batch[:, 2]).view(-1, self.embedding_dim, 1)

        # Compute scores
        scores = h @ r @ t

        # Regularization
        self.regularize_if_necessary(h, r, t)

        return scores[:, :, 0]

    def score_t(self, hr_batch: torch.LongTensor) -> torch.FloatTensor:  # noqa: D102
        h = self.entity_embeddings(hr_batch[:, 0]).view(-1, 1, self.embedding_dim)
        r = self.relation_embeddings(hr_batch[:, 1]).view(-1, self.embedding_dim, self.embedding_dim)
        t = self.entity_embeddings.weight.transpose(0, 1).view(1, self.embedding_dim, self.num_entities)

        # Compute scores
        scores = h @ r @ t

        # Regularization
        self.regularize_if_necessary(h, r, t)

        return scores[:, 0, :]

    def score_h(self, rt_batch: torch.LongTensor) -> torch.FloatTensor:  # noqa: D102
        """Forward pass using left side (head) prediction."""
        # Get embeddings
        h = self.entity_embeddings.weight.view(1, self.num_entities, self.embedding_dim)
        r = self.relation_embeddings(rt_batch[:, 0]).view(-1, self.embedding_dim, self.embedding_dim)
        t = self.entity_embeddings(rt_batch[:, 1]).view(-1, self.embedding_dim, 1)

        # Compute scores
        scores = h @ r @ t

        # Regularization
        self.regularize_if_necessary(h, r, t)

        return scores[:, :, 0]
