# xtb_simulator

Trading bot simulator for the XTB platform. The idea is to make a simulatior that, with the parameters obtained from the calculations made through technical analysis, finds entry points in the market.

<br />
Once we have the symbol and the PIP Value (available in the borker platform), we start collecting the data for the next technical indicators:
<br />
<br />
For this strategy we will use:
 - Pivot Points(PP): To determine the supports and resistances of the current day by means of the OCLH (Open Close Low Hig) values of the previous day.
 - Stochastic Oscillator (OS): A momentum indicator comparing a particular closing price of a security to a range of its prices over a certain period of time.
<br />
We are going to calculate those values with TA-Lib library on Python.
<br />

Once we have the data we will generate a Dataframe (like an Excel sheet) to see if the last value match with our requirements, in that case we prepare our position.
<br />

Before we open our position we must determinate the <b>SIZING</b> also known as <b>AMOUNT</b> or <b>VOLUME</b>, in that case we are going to us the minimum amount (0.01)$. We also have to know our <b>FREE MARGIN (FM)</b>, the FM is the margin we have free to operate, if you want to open a position the broker wants to protect itself, so, a margin is required if the price turns agains you.
<br />

Then, in our case we are going to buy, always, we need the spread amount added in the entry price, yes, the buying price will look higher than the selling price, but profits will not appear until the selling price it's over our buy price.
<br />

To calculate <b>StopLoss (SL)</b>, were we want to cut our losses, we ar ging to usea <b>FIXED RISK</b> formula<br/>
**last_price - (FIXED_RISK * last_price)** <br/>
FIXED_RISK = Amount available to loose, in this case a 2% = 0.02
<br />

To calculate <b>TakeProfit (TP)</b>, were we want to take our profits, were are going to compare our price with the PP, if there is a PP over our price we are gonna use it.
<br />

Then an array with the entries, If we use a <b>VOLUME</b> bigger than 0.01, then it's open the possibility to open a second entry, I mean:

If we have enough <b>VOLUME</b> for more than one operation, like 0.04, one operation will have a TP at the first PP and the other operation for the next PP, Example: <br/>

Actual Market Price: 10$ <br/>
Entry 1, Vol: 0.02, SL: 8$, TP: 12$ <br/>
Entry 1, Vol: 0.03, SL: 8$, TP: 15$
<br />

Once we have the entry we save it in an array that we will iterate to see if the TP or SL has been reached, in that case we run the numbers to see if we have profits or losses.
<br />
<br />

