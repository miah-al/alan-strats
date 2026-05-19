# Binomial Option Pricing

**From a Coin Flip to Black–Scholes — no calculus required.**

First edition, 2026.

Copyright © 2026 Alan. All rights reserved.

No part of this publication may be reproduced, distributed, or transmitted in any form or by any means, including photocopying, recording, or other electronic or mechanical methods, without the prior written permission of the author, except in the case of brief quotations embodied in critical reviews and certain other non-commercial uses permitted by copyright law.

ISBN: [pending — to be assigned at publication]

Printed and bound on demand.

The author has used best efforts in preparing this book, but makes no representations or warranties with respect to the accuracy or completeness of its contents. The numerical examples are for educational purposes only and do not constitute financial advice or a recommendation to trade any particular instrument.

\newpage

## Preface

This book is a self-contained tour of the binomial option pricing model. It is written for the *quant-curious professional* — a trader, a developer, a portfolio manager — who has not seen calculus in years and would rather not need to. Every result is derived from finite sums, ratios, and combinations. Where the famous Black–Scholes formula appears in the final chapter, it appears as a *limit* of the binomial formula at fine time-steps. The limit is shown numerically and then proved using only the Central Limit Theorem; no integrals, no derivatives, no stochastic calculus.

The book has eight chapters. Chapter 0 is a math primer that collects what the rest of the book needs: probability, conditional expectation, the binomial coefficient $\binom{n}{k}$, the binomial and normal distributions, the Central Limit Theorem, and the algebra of compounding and logarithms. Chapter 1 builds the one-period binomial model and the two routes to a fair price — replication and risk-neutral expectation. Chapter 2 generalises to a multi-period tree via backward induction. Chapter 3 puts the probability bookkeeping (events, filtrations as partitions, conditional expectation) on a coin-toss space, no measure theory beyond what we actually use. Chapter 4 prices American derivatives and introduces optimal stopping. Chapter 5 develops the random walk and the *reflection principle* gradually — a single picture, then the doubling identity, then its applications. Chapter 6 prices interest-rate-dependent securities on a binomial tree. Chapter 7 — the capstone — derives the Black–Scholes call price as the limit of the binomial formula at finer and finer time-steps.

Every chapter opens with the punchline before any derivation. Every new concept gets at least one concrete numerical example with named numbers ($S_0=\$100$, $u=1.10$, $d=0.90$, $r=2\%$ throughout, unless otherwise noted). Every major section has at least one figure. The figures are colourful and they earn their space — payoff diagrams, replication tables visualised as bars, binomial trees as 2-D lattices and 3-D surfaces, the Central Limit Theorem visualised as a stack of distributions, the binomial-to-Black–Scholes convergence as a single chart.

Errata, corrections, and suggestions are welcome.

\newpage
