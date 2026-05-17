# Bibliography

A consolidated list of the case studies and named episodes cited in this guide, with the canonical reference for each. Standard textbook references for the underlying mathematical material — Shreve's *Stochastic Calculus for Finance* I and II, Hull's *Options, Futures, and Other Derivatives*, Brigo and Mercurio's *Interest Rate Models*, Gatheral's *The Volatility Surface*, Wilmott's *Paul Wilmott on Quantitative Finance*, and McNeil, Frey, and Embrechts' *Quantitative Risk Management* — are assumed as background reading and not re-listed for each topic.

## Case studies and named events

**Black Monday, 19 October 1987.** Brady Commission, *Report of the Presidential Task Force on Market Mechanisms* (January 1988). For the portfolio-insurance dynamics specifically, see Leland and Rubinstein, "The Evolution of Portfolio Insurance," in *Dynamic Hedging: A Guide to Portfolio Insurance* (1988), and Carlson, "A Brief History of the 1987 Stock Market Crash," Federal Reserve Board Finance and Economics Discussion Series 2007-13.

**LTCM collapse, August–September 1998.** Lowenstein, *When Genius Failed: The Rise and Fall of Long-Term Capital Management* (Random House, 2000). For the swap-spread arb mechanics, see also the President's Working Group on Financial Markets, *Hedge Funds, Leverage, and the Lessons of Long-Term Capital Management* (April 1999).

**Buffett's SPX long-dated puts, 2004–2008.** Berkshire Hathaway annual reports, especially the 2008 chairman's letter, which discusses the equity-put portfolio and the Black–Scholes mark-to-market dynamics under long-dated assumptions.

**2008 Global Financial Crisis.** Financial Crisis Inquiry Commission, *The Financial Crisis Inquiry Report* (January 2011). For specific securitisation and CDS mechanics, see Gorton, *Slapped by the Invisible Hand: The Panic of 2007* (Oxford, 2010).

**Flash Crash, 6 May 2010.** CFTC and SEC, *Findings Regarding the Market Events of May 6, 2010* (30 September 2010, joint report).

**Knight Capital, 1 August 2012.** SEC, *In the Matter of Knight Capital Americas LLC*, Administrative Proceeding File No. 3-15570 (16 October 2013).

**Volmageddon, 5 February 2018.** SEC and CFTC public statements and ETP issuer 8-K filings; see also the public 8-K from Credit Suisse on the VelocityShares XIV note acceleration (6 February 2018). For analytical commentary on the short-vol unwind dynamics, see Bouchaud and Bonart, "What is the Mechanism of the 5 February 2018 VIX Spike?" working paper.

**March 2020 COVID dislocation.** Federal Reserve press releases, March 2020 (15 March emergency rate cut, 17 March CPFF and PDCF announcements, 23 March open-ended QE and credit facilities). For the vol-surface evidence, see the CBOE Volatility Index historical data and IMF, *Global Financial Stability Report* (April 2020).

**Negative WTI, 20 April 2020.** CFTC Interim Staff Report, *Trading in NYMEX WTI Crude Oil Futures Contract Leading up to, on, and around April 20, 2020* (November 2020).

**GameStop short squeeze, January 2021.** SEC, *Staff Report on Equity and Options Market Structure Conditions in Early 2021* (October 2021).

**Archegos default, March 2021.** Credit Suisse, *Report on Archegos Capital Management* (Paul, Weiss external review, July 2021). See also subsequent regulatory commentary from the Federal Reserve and FINMA.

**UK LDI mini-budget crisis, 23–28 September 2022.** Bank of England, *Financial Stability Report* (December 2022) and the Governor's letter to the Treasury Select Committee dated 5 October 2022 explaining the temporary purchase facility for long-dated gilts.

**Silicon Valley Bank failure, March 2023.** Board of Governors of the Federal Reserve System, *Review of the Federal Reserve's Supervision and Regulation of Silicon Valley Bank* (April 2023, the Barr report). For the duration mechanics specifically, see also FDIC, *Material Loss Review of Silicon Valley Bank* (April 2023).

**LIBOR-to-SOFR transition.** Alternative Reference Rates Committee (ARRC) publications, especially the *Paced Transition Plan* and the *SOFR Starter Kit*; see also the joint regulatory statement of November 2020 and the ICE Benchmark Administration cessation announcement of 5 March 2021.

## Mathematical and modelling references

**Itô calculus and stochastic differential equations.** Karatzas and Shreve, *Brownian Motion and Stochastic Calculus* (Springer, 1991). Øksendal, *Stochastic Differential Equations* (Springer, 6th ed., 2003). Revuz and Yor, *Continuous Martingales and Brownian Motion* (Springer, 3rd ed., 1999) for the measure-theoretic foundations.

**Arbitrage pricing and the Fundamental Theorem.** Harrison and Kreps, "Martingales and Arbitrage in Multiperiod Securities Markets," *Journal of Economic Theory* 20 (1979). Harrison and Pliska, "Martingales and Stochastic Integrals in the Theory of Continuous Trading," *Stochastic Processes and their Applications* 11 (1981). Delbaen and Schachermayer, *The Mathematics of Arbitrage* (Springer, 2006) for the general semimartingale version.

**Black–Scholes and the PDE approach.** Black and Scholes, "The Pricing of Options and Corporate Liabilities," *Journal of Political Economy* 81 (1973). Merton, "Theory of Rational Option Pricing," *Bell Journal of Economics and Management Science* 4 (1973).

**Binomial trees.** Cox, Ross, and Rubinstein, "Option Pricing: A Simplified Approach," *Journal of Financial Economics* 7 (1979).

**Heston model.** Heston, "A Closed-Form Solution for Options with Stochastic Volatility with Applications to Bond and Currency Options," *Review of Financial Studies* 6 (1993). Albrecher, Mayer, Schoutens, and Tistaert, "The Little Heston Trap," *Wilmott Magazine* (January 2007) for the branch-cut fix in the characteristic-function formula.

**Short-rate models.** Vasicek, "An Equilibrium Characterization of the Term Structure," *Journal of Financial Economics* 5 (1977). Hull and White, "Pricing Interest-Rate-Derivative Securities," *Review of Financial Studies* 3 (1990). Ho and Lee, "Term Structure Movements and Pricing Interest Rate Contingent Claims," *Journal of Finance* 41 (1986).

**Black's formula for caps and swaptions.** Black, "The Pricing of Commodity Contracts," *Journal of Financial Economics* 3 (1976). For the modern T-forward / annuity-measure derivation, see Brigo and Mercurio, *Interest Rate Models — Theory and Practice* (Springer, 2nd ed., 2006).

**Risk measures and coherence.** Artzner, Delbaen, Eber, and Heath, "Coherent Measures of Risk," *Mathematical Finance* 9 (1999). Rockafellar and Uryasev, "Optimization of Conditional Value-at-Risk," *Journal of Risk* 2 (2000). For Basel and FRTB context: Basel Committee on Banking Supervision, *Minimum Capital Requirements for Market Risk* (BCBS d457, January 2019, as revised).

**Cornish–Fisher expansion.** Cornish and Fisher, "Moments and Cumulants in the Specification of Distributions," *Review of the International Statistical Institute* 5 (1937). For its use in delta-gamma VaR see Jorion, *Value at Risk: The New Benchmark for Managing Financial Risk* (McGraw-Hill, 3rd ed., 2006).

**Monte Carlo methods.** Glasserman, *Monte Carlo Methods in Financial Engineering* (Springer, 2003) is the standard reference for variance reduction, path-dependent payoffs, and Greeks via pathwise and likelihood-ratio methods.

**Volatility surfaces and skew.** Gatheral, *The Volatility Surface: A Practitioner's Guide* (Wiley, 2006). Derman and Miller, *The Volatility Smile* (Wiley, 2016).

**Quantitative risk management.** McNeil, Frey, and Embrechts, *Quantitative Risk Management: Concepts, Techniques and Tools* (Princeton, revised ed., 2015). For copulas and tail dependence: Nelsen, *An Introduction to Copulas* (Springer, 2nd ed., 2006).
