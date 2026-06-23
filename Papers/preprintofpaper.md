

Directional Forecasting of WTI and Brent Crude Oil
Prices: A Machine Learning Approach with
Technical Indicators at Daily, Weekly, and Monthly
## Frequencies
## Badr Alnssyan
## Qassim University
## Muhammad Ali
## Abdul Wali Khan University Mardan
## Muhammad Ahmad
## Abdul Wali Khan University Mardan
## Research Article
Keywords: Statistical models, ARIMA, Machine learning, WTI, Brent oil
## Posted Date: December 16th, 2025
DOI: https://doi.org/10.21203/rs.3.rs-8253110/v1
License:   This work is licensed under a Creative Commons Attribution 4.0 International License.
## Read Full License
Additional Declarations: No competing interests reported.

Directional Forecasting of WTI and Brent Crude
Oil Prices: A Machine Learning Approach with
Technical Indicators at Daily, Weekly, and
## Monthly Frequencies
## Badr Alnssyan
## 1
## ,  Muhammad Ali
## 2*
## ,  Muhammad Ahmad
## 2
## 1
Department of Management Information Systems College of Business
and Economics, Qassim University, Buraydah, 51452, , Saudi Arabia.
## 2
Department of Statistics, Abdul Wali Khan University Mardan,
## Mardan, 23200, Khyber Pakhtunkhwa, Pakistan.
*Corresponding author(s). E-mail(s):
## Muhammad.ali@awkum.edu.pk;
Contributing authors:b.alnssyan@qu.edu.sa;amdm8008@gmail.com;
## Abstract
Crude oil prices exhibit pronounced volatility, nonstationarity, and nonlinear
behavior, making accurate forecasting inherently challenging,particularly when
employing traditional statistical models such as the Autoregressive Integrated
Moving Average (ARIMA) model. Although classical time-series techniques
remain widely adopted by market practitioners, technical indicators have received
comparatively limited attention in the academic literature onenergy price fore-
casting. To address this research gap, the present study employssupervised
machine learning algorithms—including Support Vector Machine (SVM), Arti-
cial Neural Network (ANN), K-Nearest Neighbors (KNN), Decision Tree (DT),
Na ̈ıve Bayes (NB), and Random Forest (RF)—to forecast the directional move-
ment (up or down) of two major crude oil benchmarks, West Texas Intermediate
(WTI) and Brent, across three temporal frequencies: daily, weekly, and monthly,
for the period 2010 to 2024. While these algorithms are capable ofsolving
both regression and classication problems, this research specically formu-
lates crude oil price forecasting as a binary classication task,wherein the
target variable indicates whether the price will rise or declinein the subse-
quent time interval. Model performance is assessed using four widely accepted
classication metrics: accuracy, precision, recall, and F1-score. Empirical results
## 1

demonstrate that SVM models—particularly those employing linear and poly-
nomial kernels—consistently achieve superior forecasting accuracy compared to
other classiers across most experimental settings.
Keywords:Statistical models, ARIMA, Machine learning, WTI, Brent oil
## 1 Introduction
Crude oil remains one of the most critical commodities in the global economy, serv-
ing as a primary input in industries ranging from transportation and manufacturing
to energy and defense. Its price dynamics directly inuence ination, national GDP,
stock market indices, and the strategic decision-making of governments and corpo-
rations [
1]. Two of the most signicant crude oil benchmarks are WTI and Brent
crude oil, which are heavily traded globally, and their prices are closely monitored
by economists, investors, and policymakers. However, forecasting the future direc-
tion or magnitude of crude oil prices and other commodities remains an exceptionally
challenging task due to the volatile, nonlinear, and nonstationary nature [2], [3]. E-
cient data collection methods and the application of appropriate modelsare crucial
for producing forecasts that are better and more accurate. The classication models,
which predict the direction of stock returns, outperform traditional level estimation
models in both forecast accuracy and trading protability and yield a higher hit
rate and greater prots, especially when used with multiple threshold trading strate-
gies based on prediction condence [4]. Conventional time series forecasting models,
such as Autoregressive Integrated Moving Average (ARIMA) [5], generalized autore-
gressive conditional heteroscedasticity (GARCH) [6], and autoregressive conditional
heteroscedasticity (ARCH) [7] have been widely employed for predicting commodity
prices. These models, although statistically elegant, are based on linear assumptions
and often fail to capture the complex patterns and interactions present in oil price
dynamics, especially under the inuence of unexpected geopolitical events, demand-
supply imbalances, pandemics, and speculative trading. For instance, the COVID-19
pandemic in 2020 sent oil prices into historically negative territory for the rst time,
a phenomenon that traditional models were completely unequipped toforecast. In
response to the limitations of classical models, a growing body of research has explored
the use of machine learning (ML) techniques in forecasting nancial and economic
time series. These models have gained prominence because of theirability to learn
from vast amounts of data, model non-linear dependencies, and adapt to complex
temporal patterns without being constrained by rigid statistical assumptions [8–10].
Specically, supervised ML algorithms such as SVM, ANN, DT, NB, RF, and KNN
have shown promising results in predicting stock market trends, exchange rates, and
commodity prices [11–13]. Despite this progress, the majority of existing literature on
crude oil forecasting tends to approach the problem as a regression task,where the
goal is to predict the exact price value at a future time point [
14]. However, from a
practical perspective particularly in trading and investment decisions it is often more
useful to predict the direction of price movement (up or down) rather than the precise
## 2

value. This classication-based approach aligns more closely with the needs of mar-
ket participants, enabling the formulation of buy/sell strategies and risk mitigation
plans [15]. In prior research, three principal approaches have been employed to fore-
cast either the directional movement or the actual values of crude oil prices. The rst
approach is referred to as technical-based studies [16–19] the second as hybrid machine
learning methods [20–24], and the third as deep learning techniques [25–29]. Surpris-
ingly, there remains a notable lack of studies that systematically compare multiple
ML classiers for directional oil price forecasting using a robust experimental setup
and extended time horizon. The primary goal of this research work is to assess how
well supervised machine learning techniques can classify the directional movement of
crude oil prices and to determine which algorithm delivers the highest accuracy and
consistency. To achieve this, we evaluate the performance of six models namely SVM,
ANN, KNN, DT, NB, and RF utilizing both WTI and Brent crude oil prices, using
datasets aggregated at daily, weekly, and monthly intervals. Our ndings are intended
to provide actionable guidance for policymakers, investors, and energyanalysts in
selecting the most eective model for forecasting oil price movements. Furthermore,
this investigation is guided by the following research questions:
## •
Can supervised machine learning algorithms eectively predict the directional
movement (increase or decrease) of WTI and Brent crude oil prices?
## •
Among the classiers—SVM, ANN, KNN, DT, NB, and RF—which model delivers
the highest accuracy and the most balanced performance across multipleevaluation
metrics?
## •
How does model performance dier between the WTI and Brent benchmarks, and
are there consistent patterns indicating the superiority of a particular algorithm?
By answering these questions, this study contributes both to themethodological lit-
erature on oil price forecasting and to practical decision-making, oering stakeholders
actionable guidance for improving predictive capabilities in volatile, data-rich envi-
ronments. The remaining sections of the paper is structured in thefollowing order:
Section 2 outlines the material and methods, such as data preprocessing, technical
indicators, prediction models and accuracy metrics; Section 3 presents results and dis-
cussion; detail conclusion of the study is provided in Section 4; and nally to end this
paper limitation of the study is provided in Section 5.
2 Materials and Methods
In this section, we provide a detailed overview of the materials andmethods employed
in the study. Specically, we discuss the technical indicators selected for feature con-
struction, the prediction models applied to forecast the directional movement of both
WTI and Brent crude oil prices, and the evaluation metrics used to assess the fore-
casting performance. Each component is described to oer a clear understanding of
the methodological framework adopted in this research.
## 3

## 2.1 Data Preprocessing
In this study, fourteen years of data—from January 4, 2010, to May 24, 2024—cov-
ering two major crude oil benchmarks, Brent and WTI, are utilized.We extracted
prices at daily, weekly, and monthly frequencies from investing.com [30], accessed on
May 24. The dataset was split using a time-based holdout approach: the rst 80% of
observations were used for training and the remaining 20% for testing, thereby pre-
serving the temporal order of the crude oil time series. After downloading, the data
were cleaned in Excel to remove any missing values. Following this preprocessing step,
seventeen technical indicators were derived from the opening, high, low, close, and
volume series using established formulas. These indicators were then used as input
features for the machine learning models. The specic details andrelevance of these
technical indicators are discussed in the following subsection.
## 2.2 Technical Indicators
Technical indicators highlight specic aspects of price or volume behavior on a stock
chart, providing valuable insights for analysis [
31]. They generate entry and exit sig-
nals for stock trading systems and assist in identifying protable market opportunities
through systematic stock screening. This helps to minimize psychological pressure dur-
ing decision-making. In Table1, the details of the 17 technical indicators used as input
features for various supervised ML techniques to predict the directional movement
(up or down) of both WTI and Brent crude oil across three frequency domains—daily,
weekly, and monthly—are presented.
After calculating technical indicators, the next task is to convert them and the
daily closing prices across three frequency horizons (daily, weekly, and monthly) into
a binary classication problem. For this purpose, we encoded the next period’s direc-
tional movement as a binary variable: “0” if the closing price decreasesand “1” if it
increases. Finally, all technical indicators were scaled using min–max scaling, using
the following mathematical equation.
## Y
min−max
## =
## Y−Y
min
## Y
max
## −Y
min
## .(1)
## In (
## 1),Y
min
andY
max
are the minimum and maximum values of each feature,
respectively. The min–max scaling was chosen for its robustness to outliers compared
to standard normalization. With the data preprocessed and features scaled appro-
priately, the next step involves selecting and conguring the predictive models for
directional forecasting.
## 2.3 Prediction Models
This study employs a suite of six advanced prediction models to capture the complex
and nonlinear behavior of crude oil prices. These models have been widely recognized
in nancial time-series forecasting due to their ability to learn temporal dependencies,
extract hidden patterns, and enhance predictive accuracy. In the following subsections,
we briey describe the architecture and methodological foundations ofeach model
used in this study.
## 4

Table 1Summary of Technical Indicators
IndicatorsPurpose / DescriptionFormula
Pivot Point (PP)Identies support and resistance levels;
reects market sentiment
## P P=
High+Low+Close
## 3
Support 1 S(1)First support level (price oor)S1 = (P P×2)−High
Support 2 S(2)Deeper support level below S1S2 =P P−(High−Low)
Resistance 1 R(1)First resistance level (price ceiling)R1 = (P P×2)−Low
Resistance 2 R(2)Stronger resistance level above R1R2 =P P+ (High−Low)
## Simple Moving Aver-
age (SMA)
Smooths price data to show trendsSMA=
## P
## 1
## +P
## 2
## +···+P
t
t
## Exponential  Moving
Average (EMA)
Similar to SMA, but gives more weight
to recent prices
## EMA
t
## = (P
t
α) +EMA
t−1
## (1−α)
## Relative    Strength
Index (RSI)
Momentum oscillator identifying over-
bought/oversold zones
## RSI= 100−
## (
## 100
## 1+
## U
## D
## )
Williams %RIdenties overbought/oversold%R=
Highest High−Close
Highest High−Lowest Low
## ×100
Rate   of   Change
## (ROC)
Measures % change from past prices.ROC=
## (
## C
t
## −C
t−n
## C
t−n
## )
## ×100
PercentagePrice
Oscillator (PPO)
Momentumindicator;dierence
between EMAs
## P P O=
## EMA
fast
## −EMA
slow
## EMA
slow
Momentumspeed of price movementMomentum=C
t
## −C
t−4
## Commodity Channel
Index (CCI)
Shows price variation from mean; iden-
ties overbought/oversold
## CCI=
T ypical P rice−MA
0.015×Mean Deviation
Stochastic %KDetects momentum by comparing close
to price range
## %K=
Close−Lowest Low
Highest High−Lowest Low
## ×100
Stochastic %DSignal line (3-days SMA of %K).%D=
## ∑
## %K
i
n
Disparity IndexShows deviation of current price from
## MA
## Disparity=
## C
t
## MA
t
## ×100
OSCPTrend detection using the dierence
between two moving averages
## OSCP=
## MA
## 5
## −MA
## 10
## MA
## 5
## 2.3.1 Decision Tree Model
The decision tree learner predicts outcomes by splitting data fromthe root to leaf
nodes using feature variables. It aims to maximize purity at each split, commonly
measured by entropy:
## Entropy =−
c
## X
i=1
## F
i
log
## 2
## (F
i
## )(2)
## In (
2)cis the number of classes (two in this case), andF
i
is the proportion of obser-
vations in classi. Entropy ranges from 0 (pure) to 1 (most impure). Other metrics like
the Gini index, Chi-square, and gain ratio are also used to guide optimalsplits [32].
2.3.2 Articial Neural Network (ANN)
In 1944, Warren McCullough and Walter Pitts introduced a groundbreaking tech-
nique known as the neural network (NN), inspired by the functioningof the human
## 5

brain in a natural setting [33]. Similar to a neural net, this nonlinear mapping struc-
ture forms a network that reects the connectivity of neurons in thebrain. ANN,
that analyzes information through thousands of articial neurons connectedthrough
nodes, is modeled after the brain’s millions of linked neuron nuclei. When using neu-
ral networks, data is input and an output is produced using a weightedalgorithm.
Like human beings, who follow instructions and guidance to draw conclusions, ANNs
follow an established theory called backpropagation for direction and weight modi-
cation throughout training. Neural networks may adapt and learn from data through
this repeated process, which eventually improves their accuracy in task execution and
prediction making. The following Fig.1depicts the general pattern of the resilient
back-propagation learning process proposed in this study for training afour-layer feed-
forward neural network with two hidden nodes. Employing resilient backpropagation
instead of conventional BPNN oers the advantage of eliminating the need fora learn-
ing rate and signicantly reducing training time for the neural network algorithm.
Fig. 1General architecture of ANN model
2.3.3 Random Forest (RF)
Random Forest (RF), introduced by [34] and highlighted by [35], is a powerful ensem-
ble learning method that builds multiple regression trees usingbootstrapped subsets
of data. Each tree is grown independently, and at every split, a random subset of pre-
dictors is considered to reduce correlation among trees and prevent overtting. The
nal prediction is obtained by averaging the outputs of all individual trees. The model
minimizes Mean Squared Error (MSE) at each node to ensure optimal splits. The
## 6

ensemble prediction fromMtrees is as follows:
## F
## 0
## (x) =
## 1
n
n
## X
i=1
## (y
i
## −γ)
## 2
## (3)
## F
## 0
## (x) =
## 1
n
n
## X
i=1
## (y
i
## −γ)
## 2
## (4)
This aggregated prediction stabilizes outputs and enhances generalization, making RF
one of the most robust algorithms in supervised learning.
2.3.4 Na ̈ıve Bayes (NB)
A well-known classication method based on probability theory—specically, Bayes’
theorem—is the NB algorithm [
36]. The NB method is recognized for its clarity and
ease of training and implementation. However, it is referred to as ”na ̈ıve” because it
relies on two fundamental assumptions. First, it assumes that the predictive (prognos-
tic) features are conditionally independent given the class label, thereby simplifying
the complex relationships among variables. Second, it assumes that no hidden or
latent attributes inuence the prediction process, further streamlining the modeling
approach. Even with such changes, NB remains a compelling approach, as itsfounda-
tion is based on probabilistic theory and it oers a successful, computationally ecient
algorithm for data categorization tasks. Its simplicity makes it particularly useful in
applications where computational eciency and interpretability are important. By
leveraging its probabilistic framework to uncover underlying patterns in data, NB helps
both academics and practitioners derive practical insights and make well-informed
decisions.
2.3.5 K-Nearest Neighbors (KNN)
The algorithm for KNN was rst suggested by Evelyn Fix and Joseph Hodges in
## 1951 [
37], and is a well-known supervised machine learning technique used both for
classication and regression problems. Following is the step-by-step procedure of this
method.
- The rst step is to slice the data in both training and testing, and then the
training data set, which consists of valid labels, is used by KNN to build
its architecture.
- In the second step metrics like Cosine similarity, Manhattan distance, or
Euclidean distance are used to calculate the dierences betweeneach new,
unlabeled data point and every other point in the learning set
- In this step, the algorithm selects thekclosest data points to the new
observation using a distance metric.
- At this stage for classication tasks, the labeled classes of the newly
acquired data point’sknearest neighbors are used to gure out the cate-
gory for the subsequent data point, whereas in regression problems, ituses
the average of the target values of the ‘k’ nearest neighbors.
## 7

- And nally, using the results of the majority vote or average stage, the
projected class name or value is applied to the new data point.
Although KNN is well renowned for its eciency and simplicity, it canbe com-
putationally expensive, particularly when dealing with huge datasets because every
prediction needs storing and looking over the full training dataset. Also, the algo-
rithm’s eectiveness can be greatly aected by the parameter ‘k’ selection, which
frequently necessitates trial and error to determine the ideal value. Apart from these
disadvantageous, this novel method has a wide range of application in many elds
such as bioinformatics [38], pattern recognition [39], image recognition [40], and
recommendation systems [41].
2.3.6 Support Vector Machine (SVM)
SVM developed by Vapnik in 1995 [
42], is a widely used supervised learning algo-
rithm applicable to both classication and regression tasks. Unlike neural networks,
which minimize empirical error, SVM relies on statistical learningtheory and struc-
tural risk minimization [43]. It aims to nd an optimal hyperplane that maximizes
the margin between classes in an n-dimensional feature space. For linearly separable
data, SVM directly constructs this hyperplane. However, for nonlinear problems, SVM
employs kernel functions—such as linear, polynomial, and radial basis function (RBF)
kernels—to project the data into a higher-dimensional space wherelinear separation
becomes possible. The decision function is given by:
f(x) = sgn

n
## X
i=1
y
i
α
i
K(x, x
i
## ) +b
## !
## (5)
## Whereα
i
is Lagrange multipliers obtained by solving the dual optimization problem:
max
α
## 
## 
n
## X
i=1
α
i
## −
## 1
## 2
n
## X
i=1
n
## X
j=1
α
i
α
j
y
i
y
j
## K(x
i
, x
j
## )
## 
## 
## (6)
The dual problem is solved under the constraints 0≤α
i
≤Cand
## P
n
i=1
α
i
y
i
= 0, i=
1,2, . . . , n. The parameter C controls the trade-o between maximizing the margin
and minimizing classication error. After training the above-dened prediction models,
their performance was evaluated using four classication metrics, such as F1 score,
precision, recall, and accuracy. Details of these performance metrics are dened in the
following subsection.
## 2.4 Accuracy Metrics
The main purpose of this study is to predict the directional movement (upward or
downward) of WTI and Brent crude oil prices across three temporal frequencies,
such as daily, weekly, and monthly. As such, the problem is formulatedas a binary
classication task, where the model assigns each observation to one of twoclasses:
## 8

## •
Positive (P): Upward price movement
## •
Negative (N): Downward price movement
To evaluate the performance of the dierent supervised machine learning classication
models used for these predictions, a set of standard accuracy metrics derived from
the confusion matrix presented in the following Table
2, which summarizes the actual
vs. predicted class labels. In the above table, True Positive (TP)indicates that the
Table 2Confusion matrix to nd accuracy for predicting the
direction movement of WTI and Brent
Actual Class    Predicted: UpPredicted: DownTotal
Actual: UpTP (True Positive)   FN (False Negative)P
Actual: Down   FP (False Positive)   TN (True Negative)N
TotalPNP+N
model correctly predicts an upward movement when the actual priceincreased. False
Negative (FN) occurs when the model predicts a downward movement,but the actual
price goes up. True Negative (TN) means the model correctly predictsa downward
movement when the actual price decreased. Lastly, False Positive (FP) refers to the
case when the model predicts an upward movement, but the price actually declined.
Based on these components, the following accuracy metrics are computed to assess
the forecast accuracy of dierent models.
## Accuracy=
## (T P+T N
## (P+N)
## (7)
The accuracy metric dened in (
7) reects the overall proportion of correct predic-
tions for both upward and downward movements. However, in directionalprediction
tasks with potential class imbalance for example, more ”up” days than ”down” days,
therefore accuracy alone may be insucient.
P recision=
## T P
## T P+F P
## (8)
Precision evaluates the model’s ability to correctly identify upward movements. It
answers the question, ”When the model predicts an upward movement, how often is
it correct?” In the context of trading strategies, high precision reduces the likelihood
of acting on false alarms such as buying when the price actually declines.
## Recall=
## T P
## P
## (9)
Recall measures the model’s ability to detect actual upward movements. It answers:
”Out of all real upward movements, how many did the model correctly predict?” High
## 9

recall is crucial in scenarios where missing upward trends may leadto missed prot
opportunities.
## Accuracy=
## T P+T N
## P+N
## (10)
Specicity evaluates how well the model detects downward movements, that is avoids
false positives. It ensures the model does not frequently mistake actual declines as
rises, which could be costly for short-selling or hedging strategies.
## F1 Score =
2×Precision×Recall
## Precision + Recall
## (11)
The last performance dened in equation (
11) is the F1 score. This performance metric
balances precision and recall by taking their harmonic mean. This metric is especially
important when the cost of both false positives and false negatives is signicant as in
high-stakes oil trading decisions. In the context of forecasting the directional move-
ment of WTI and Brent crude oil, these metrics provide a multifaceted evaluation of
classication performance across daily, weekly, and monthly time frames. They help
assess not only how many directional changes were predicted correctly(accuracy) but
also the quality of upward movement predictions (precision) and themodels’ ability
to detect real market trends.
3 Results and Discussion
In this section, the ndings of the study are analyzed and discussed in detail. The pre-
dictive performance of various machine learning models, includingSVM, RF, ANN,
NB, and KNN, is evaluated using multiple technical indicators as input features.
To assess the eectiveness of these models in forecasting crude oil prices, the study
employs key performance metrics, namely F1 Score, Precision, Accuracy, and Recall.
The following subsection comprehensively discusses the descriptive statistics of both
WTI and Brent oil, followed by the comparison of dierent models, and lastly, for
better understanding, the graphical visualization of the accuracy metrics.
3.1 Descriptive Statistics of the Data
The following Tables
3and4present the descriptive statistics of WTI and Brent
crude oil across daily, weekly, and monthly intervals. Key metrics such as minimum,
## Q
## 1
, median, mean,Q
## 3
, and maximum values highlight the distribution, volatility,
and trends in crude oil prices. Analyzing these statistics across dierent timeframes
helps better understand market behavior and supports the evaluationof forecasting
model performance under varying conditions. The descriptive statistics presented in
the above Table3oer crucial insights into the behavior of WTI crude oil prices and
trading volume across dierent time frequencies, such as daily, weekly, and monthly.
These metrics, including the minimum, median, mean, quartiles, and maximum, are
fundamental in understanding the structure and variability of the data before apply-
ing supervised machine learning techniques. For instance, the daily closing price shows
a wide range, from a minimum of –37.63 to a maximum of 123.7, with a mean of 71.71
## 10

Table 3Statistical summary of WTI crude oil prices across dierent
frequency domains (daily, weekly and monthly)
Frequency   Variable   MinQ
## 1
Median   MeanQ
## 3
## Max
DailyClosing    -37.63    52.77   72.6771.70   90.20    123.70
## Open-14.00    52.77   72.7671.73   90.28    124.66
## High13.6953.51   73.9372.76   91.46    130.50
## Low-40.32    52.08   71.5370.59   88.59    120.79
## Change   -305.97   -1.10   0.09-0.06   1.2137.66
WeeklyClosing    16.9452.91   73.2071.95   90.795   120.67
## Open16.8452.86   73.2972.01   90.88    121.33
## High18.2654.35   75.5274.27   93.18    130.50
## Low-40.32    51.22   70.4169.31   87.23    117.14
## Change   -29.31    -2.51   0.280.122.6031.75
MonthlyClosing    18.8453.27   73.9572.02   91.38    114.67
## Open19.0453.42   73.6272.04   91.36    115.40
## High29.1355.37   79.2976.84   95.91    130.50
## Low-40.32    49.10   66.8666.43   85.11    105.31
## Change   -54.24    -5.86   1.470.646.2788.38
and a median of 72.67, reecting high short-term volatility. In contrast, the monthly
closing price ranges from 18.84 to 114.67, with a mean of 72.03 and a median of 73.95,
indicating more stable long-term trends. The low price also demonstrates extreme
behavior, particularly at the daily level, where it drops to –40.32, highlighting periods
of severe market stress. Such variations are crucial for choosing appropriate models and
understanding the data’s sensitivity to outliers. Similarly, trading volume shows large
dierences across frequencies. The average daily volume is approximately 386,825,
whereas the average monthly volume rises sharply to over 7.8 million,showing how
investor activity aggregates over time and aects model inputs dierently. The change
variable, representing price movement, also shows greater variability in daily data
(ranging from –305.97 to 37.66) compared to monthly data (–54.24 to 88.38), empha-
sizing the need to handle volatility carefully in short-term forecasts. These statistical
patterns help determine whether to use models suited for volatile, high-frequency data
or for more stable, long-term forecasting. Therefore, a clear understanding of these
descriptive statistics is essential to guide model selection, preprocessing techniques,
and the interpretation of results in supervised machine learning applications.  Simi-
larly, Table
4presents the descriptive statistics for Brent crude oil pricesand trading
volumes across daily, weekly, and monthly frequencies. These statistics serve the same
critical purpose, which is oering a foundational understanding of the data before
applying supervised machine learning techniques. The observedmetrics, including
minimum, quartiles, median, mean, and maximum values, help capturethe distribu-
tion, central tendency, and volatility in Brent crude oil prices over time. At the daily
level, Brent’s closing price ranges from a minimum of$19.33 to a maximum of$127.98,
with a mean of$78.41 and a median of$76.91. Similar patterns are observed in the
open, high, and low prices, with the daily high peaking at$139.13 and the low drop-
ping to$15.98, indicating sharp intraday uctuations during periods of market stress.
These extreme values are relevant for understanding model behavior under volatile
## 11

Table 4Statistical summary of Brent crude oil prices across dierent
frequency domains (daily, weekly and monthly)
Frequency   Variable   MinQ
## 1
Median   MeanQ
## 3
## Max
DailyClosing    19.33   58.44   76.9178.40   103.01   127.98
## Open19.90   58.41   76.9878.39   102.96   130.28
## High21.29   59.27   77.825    79.42   104.34   139.13
## Low15.98   57.52   75.6677.30   101.69   125
## Change   -24.40   -0.98   0.090.026   1.0921.02
WeeklyClosing    21.44   58.58   76.7978.46   103.17   126.65
## Open21.55   58.32   76.9178.45   103.12   126.58
## High27.88   60.67   78.8580.74   106.22   139.13
## Low15.98   56.50   74.2475.86   99.57    122.71
## Change   -25.23   -2.16   0.320.122.3936.82
MonthlyClosing    22.74   58.16   77.4278.57   102.37   125.89
## Open25.99   58.02   77.6978.30   101.90   126.10
## High36.463.15   81.7283.28   107.40   139.13
## Low15.98   5471.1973.14   96.93    120.97
## Change   -54.99   -4.74   1.010.556.4539.81
conditions, especially when short-term predictions are involved.As the data frequency
shifts to weekly and monthly, the volatility smooths out, but substantial variation
remains. For example, the monthly closing price ranges from$22.74 to$125.89, with
a mean of$78.57, while the high price reaches$139.13, indicating that even on a
longer time scale, signicant price swings occur. These trends are crucial for select-
ing forecasting horizons and understanding model stability. Volumestatistics show a
clear increase with frequency aggregation. The average daily volume is approximately
223,984, increasing to 1.08 million weekly, and further to 4.66 million monthly. Such
trends highlight how volume accumulates over time and reinforces its importance as
an input variable for capturing market participation and trading intensity. The change
variable, capturing percentage shifts, ranges from –24.4% to +21.02% at the daily level
and expands to –54.99% to +39.81% monthly, though the average monthly change
remains relatively moderate at 0.55%. These values again underscore the high volatil-
ity and the need for careful preprocessing and normalization when these features are
used in supervised learning models.
## 3.2 Feature Importance Analysis Using Random Forest
To evaluate the relevance of each technical indicator in predicting the directional
movement of crude oil prices, a feature importance analysis was conducted using the
Random Forest classier. This method provides a robust mechanism for identifying
the contribution of each input feature based on its impact on the model’s predictive
performance. The results presented in the following Fig
2indicate that all 17 techni-
cal indicators exhibit meaningful importance scores, supporting their inclusion in the
supervised machine learning models. Specically, the top 10 indicators yielded impor-
tance scores exceeding 0.05, while the remaining seven (R
## 2
## ,S
## 2
## , SMA14, EMA14,R
## 1
## ,
## S
## 1
, and PP) maintained values above 0.04. This consistent performance acrossall
## 12

indicators suggests that each feature contributes valuable information for directional
forecasting and none were excluded. These ndings arm the eectiveness of the cho-
sen indicators and justify their use as inputs in the classication models for WTI
and Brent crude oil price movement prediction in three dierenttime domains (daily,
weekly, and monthly).
Fig. 2Feature selection score using random forest for WTI and Brentoil across three dierent
frequencies (daily, weekly, and monthly)
3.3 Optimization of Parameters Using Grid Search With Time
Series Cross-Validation (GridSearchTSCV)
To ensure a robust evaluation of model performance over time-dependent data (such
as daily, weekly, and monthly of WTI, and Brent crude oil prices), we used Grid Search
in combination with Time Series Cross-Validation. This approach is critical for time
series forecasting tasks, as it maintains the temporal order of observations and avoids
data leakage. Instead of standard K-fold cross-validation (which randomly shues
data), we used the Time Series Split (number of splits=5), which performs forward-
chaining validation. This divides the time series data into ve sequential training and
test sets, ensuring that the training set always precedes the test set chronologically
and each subsequent split includes more data for training, mimicking real-world fore-
casting where future data is not available at training time. This method was integrated
with Grid Search CV, where a grid of hyperparameter combinations was evaluated
for each model using these time-aware splits. The best parameterset was selected
based on average cross-validation accuracy across the 5 folds. This approach provides
a more realistic and reliable measure of how each model is expected toperform in
production settings where future values are unknown at training time. The following
## Tables
5and6shows the summary of the optimized parameters and cross-validation
(CV) accuracies for various supervised machine learning models, including SVM (lin-
ear, RBF, and polynomial kernels), ANN, KNN, DT, NB, and RF for both WTI and
## 13

Brent oil daily closing prices across three frequency horizons suchas daily, weekly and
monthly. After identifying the optimal hyperparameters for each model through Grid-
Search with time series cross-validation, the next step involves using these parameters
to train the models and generate predictions on the test dataset. The primary objec-
tive of employing cross-validation is to establish a consistent evaluation framework
across all models, thereby minimizing the risks of undertting and overtting. The
following subsection presents a detailed assessment of the predictive performance of
each model using standard classication metrics, including accuracy, precision, recall,
and F1 score.
Table 5GridSearchTSCV results for WTI closing price direction (up or down) prediction in three dierent
frequency domains
FrequencyModelBest parametersAccuracy
DailySVM linearC=0.010.5054
SVM RBFC=1,γ=0.10.5099
SVM polynomialC=1, degree=4,γ=scale0.5272
ANNActivation=tanh,α=0.001, hidden layer sizes=50, learn-
ing rate=constant
## 0.5054
KNNMetric=Manhattan,Numberofneighbors=9,
weights=distance
## 0.4986
Decision TreeCriterion=Gini, Max depth=10, min sample split=50.5336
Na ̈ıve BayesN/A (No tunable parameters used)0.5018
Random ForestCriterion=Entropy, Max depth=10, min samplesplit=10   0.5050
WeeklySVM linearC=0.010.5196
SVM RBFC=10,γ=0.10.5299
SVM polynomialC=0.1, degree=2,γ=scale0.5526
ANNActivation=tanh,α=0.0001,  hidden  layer  sizes=100,
learning rate=constant
## 0.5113
KNNMetric=Manhattan,Numberofneighbors=3,
weights=uniform
## 0.5340
Decision TreeCriterion=Entropy, Max depth=10, min samplesplit=2    0.5567
Na ̈ıve BayesN/A (default parameters used)0.5052
Random ForestCriterion=Entropy, Max depth=5, min sample split=5,
number of estimators=100
## 0.5299
MonthlySVM linearC=0.010.5300
SVM RBFC=10,γ=0.010.5300
SVM polynomialC=1, degree=3,γ=scale0.5600
ANNActivation=tanh,α=0.0001, hidden layer sizes=50,50,
learning rate=constant
## 0.5400
KNNMetric=Manhattan,Numberofneighbors=3,
weights=distance
## 0.5900
Decision TreeCriterion=Entropy,  Max  depth=None,  min  sample
split=2
## 0.5700
Na ̈ıve BayesN/A (default parameters used)0.5200
Random ForestCriterion=Gini, Max depth=5, min sample split=5, num-
ber of estimators=50
## 0.6100
## 14

Table 6GridSearchTSCV results for Brent closing price direction (up or down) prediction in three dierent
frequency domains
FrequencyModelBest ParametersAccuracy
DailySVM linearC=0.010.5099
SVM RBFC=10,γ=0.010.5116
SVM polynomialC=1, degree=4,γ=scale0.5249
ANNActivation=ReLU,α=0.001, hidden layer sizes=(50,50),
learning rate=constant
## 0.5014
KNNMetric=Manhattan,Numberofneighbors=3,
weights=uniform
## 0.4949
Decision TreeCriterion=Entropy, Max depth=10, min samplesplit=5    0.5233
Na ̈ıve BayesN/A (default parameters used)0.4957
Random ForestCriterion=Entropy, Max depth=10, min samplesplit=2,
number of estimators=50
## 0.5254
WeeklySVM linearC=0.010.4990
SVM RBFC=1,γ=0.010.4928
SVM polynomialC=0.1, degree=3,γ=scale0.5320
ANNActivation=ReLU,α=0.0001,  hidden  layer  sizes=50,
learning rate=constant
## 0.5093
KNNMetric=Euclidean,Numberofneighbors=3,
weights=uniform
## 0.5052
Decision TreeCriterion=Entropy, Max depth=10, min samplesplit=5    0.5505
Na ̈ıve BayesN/A (default parameters used)0.4948
Random ForestCriterion=Gini, Max depth=10, min sample split=5,
number of estimators=50
## 0.5072
MonthlySVM linearC=0.010.5600
SVM RBFC=10,γ=0.010.5800
SVM polynomialC=1, degree=3,γ=auto0.5500
ANNActivation=ReLU,α=0.001, hidden layer sizes=50, learn-
ing rate=constant
## 0.5700
KNNMetric=Euclidean,Numberofneighbors=3,
weights=uniform
## 0.5000
Decision TreeCriterion=Entropy, Max depth=3, min sample split=20.5700
Na ̈ıve BayesN/A (default parameters used)0.5100
Random ForestCriterion=Gini, Max depth=10, min sample split=2,
number of estimators=100
## 0.5800
3.4 Comparison of Dierent Models
To evaluate the predictive performance of various machine learning models on WTI
crude oil prices, a set of accuracy metrics was computed across dierent temporal
frequencies. Each model was trained using grid search with 5-fold time series cross-
validation to ensure consistent tuning and to minimize the risk of overtting. The
detailed results are presented in the following Table
- Based on the results the best
model for daily frequency is SVM Linear, which achieved the highest F1 score of 0.6963
and perfect recall of 1.0. This means it successfully identied all actual upward move-
ments in crude oil prices, making it highly eective for daily predictions where missing
a rise is more critical than generating false alarms. For weekly frequency, the best
model is SVM Polynomial with an F1 score of 0.7200 and perfect recall. It consistently
## 15

Table 7Accuracy metrics of WTI crude oil prices across dierent frequency
domains (daily, weekly and monthly)
Frequency   ModelF1 score   Precision   Accuracy   Recall
DailySVM Linear0.6963   0.5391    0.5341    1.0000
## SVM RBF0.60060.53520.51400.6842
SVM Polynomial0.67030.53330.52610.9022
## ANN0.60510.54400.52480.6817
## KNN0.52010.53740.50330.5038
## Decision Tree0.59250.51680.49000.6942
## Na ̈ıve Bayes0.51530.52470.49130.5063
## Random Forest0.60540.53230.51140.7018
WeeklySVM Linear0.50330.54280.48970.4691
## SVM RBF0.57660.57310.53060.5802
SVM Polynomial  0.7200   0.5925    0.5714    1.0000
## ANN0.51660.55710.50340.4815
## KNN0.56440.56100.51700.5679
## Decision Tree0.69040.58620.58500.8395
## Na ̈ıve Bayes0.50000.57140.51020.4444
## Random Forest0.63490.55560.53060.7407
MonthlySVM Linear0.50001.0000    0.67740.3333
## SVM RBF0.45160.43750.45160.4666
SVM Polynomial0.56410.45830.45160.7333
## ANN0.58820.52630.54840.6667
## KNN0.52940.47370.48390.6000
## Decision Tree0.60470.46430.45160.8667
## Na ̈ıve Bayes0.23531.00000.58060.1333
## Random Forest0.54550.50000.51610.6000
captured all up movements while maintaining reasonable precision, making it suitable
for short-term trading decisions. For monthly frequency, the Decision Tree model per-
formed the best with an F1 score of 0.6047 and a high recall of 0.8667. It eectively
identied most monthly upward trends, making it a reliable choice for longer-term
forecasts despite having moderate precision. As a trader, the best-performing mod-
els across each frequency oer dierent strategic advantages based on howoften you
trade and your tolerance for risk. For daily trading, the SVM linear model is highly
benecial because it captures all the upward movements in crude oilprices, as shown
by its perfect recall of 1.0. This means the trader won’t miss any protable ”buy”
opportunities. Although the precision is moderate, resulting in some false signals, a
trader who prefers not to miss any potential gains—even at the cost of a fewincor-
rect entries—can benet from this model’s aggressive signaling. In weekly trading, the
SVM Polynomial model provides a strong balance with a high F1 score and perfect
recall. This means the trader can rely on it to catch every signicant weekly price
increase while still maintaining a reasonable precision. It suits swing traders who pre-
fer more condent signals and want to act on every potential upward trend without
excessive false trades. For monthly trading, the decision tree model stands out with
its high F1 score and very strong recall. This is ideal for position traders who focus on
long-term trends. The model ensures that most major upward price moves are cap-
tured, helping the trader make timely entry decisions. Even though it may occasionally
## 16

Table 8Accuracy metrics of Brent crude oil prices across dierent
frequency domains (daily, weekly and monthly)
Frequency   ModelF1 score   Precision   Accuracy   Recall
DailySVM Linear0.56450.51680.48910.6218
## SVM RBF0.62680.52770.51080.7715
SVM Polynomial   0.67930.54730.52920.9543
## ANN0.47490.52800.49190.4315
## KNN0.52700.53390.50270.5203
## Decision Tree0.63690.53860.52700.7792
## Na ̈ıve Bayes0.53490.50920.47840.5635
## Random Forest0.57110.53170.50680.6168
WeeklySVM Linear0.57800.53190.50340.6329
## SVM RBF0.62940.52540.50340.7848
SVM Polynomial   0.68160.57770.55700.9620
## ANN0.52940.49450.45580.5696
## KNN0.61710.56250.54420.6835
## Decision Tree0.59490.50000.46260.7342
## Na ̈ıve Bayes0.54190.55260.51700.5316
## Random Forest0.62770.54130.52380.7468
MonthlySVM Linear0.61110.52380.54830.7333
## SVM RBF0.50000.47050.48380.5333
SVM Polynomial   0.66660.57820.70611.0000
## ANN0.53330.53330.54840.5333
## KNN0.57890.47830.48390.7333
## Decision Tree0.61540.50000.51610.8000
## Na ̈ıve Bayes0.42110.42130.64520.2667
## Random Forest0.40000.40000.41940.4000
give false positives, its ability to identify almost all protable long-term trends makes
it a valuable tool for traders planning their investments on a monthlyhorizon. Sim-
ilarly, the same grid search with the time series cross-validation approach was used
to predict the direction movement (up or down) of Brent oil across three frequency
domains, such as daily, weekly, and monthly. The following Table8shows results of the
dierent performance metrics, such as F1 score, precision, accuracy, and recall. The
accuracy metrics presented in the above table for Brent crude oil prices across dier-
ent frequencies reect performance under a consistent and rigoroustraining approach.
All models were trained using the same grid search combined with 5-fold time series
cross-validation, which ensures that each model was optimized in a uniform environ-
ment and helps prevent overtting, which is especially importantwhen working with
sequential data like time series. In the daily frequency, SVM Polynomial achieved the
highest F1 score of 0.6793 and a very strong recall of 0.9543, making it highly eec-
tive at capturing the direction of movement (up or down)—an essentialquality for
short-term trading decisions. The DT also performed well with an F1score of 0.6369
and high recall, oering a simple yet fairly accurate option. In the weekly setting,
the SVM Polynomial model again led the performance with an F1 score of 0.6816
and a recall of 0.9620, conrming its robustness across slightly longer horizons. The
KNN and Random Forest models also performed well, showing balanced metrics that
## 17

suggest reliable generalization. These results, produced under the consistent cross-
validation setup, give traders condence in the models’ ability to generalize to unseen
weekly data. At the monthly level, SVM Polynomial maintained its position as the
most eective model, with a perfect recall of 1.0 and the highest F1 score of 0.6667,
highlighting its ability to fully capture all positive class events. This makes it particu-
larly useful for long-term investment planning where missing a major trend could have
a signicant impact. Models like SVM Linear and DT also performed decently, while
NB and RF showed weaker performance in this context, suggesting limited suitability
for monthly trend prediction. To complement the numerical results presented in the
table, heatmaps were generated to provide a visual comparison of model performance
across dierent frequency domains. This graphical representation aligns with the tab-
ulated metrics, making it easier to observe performance patterns andidentify the most
eective models at a glance. The above Figures3, and4shows the heatmaps of dier-
ent forecast accuracies for both WTI and Brent oil. Overall, the application of grid
Fig. 3Heatmap of accuracy measures of predicting the direction movement (up or down) of WTI
daily closing prices across three frequency horizons (daily, weekly, and monthly).
search with 5-fold time series cross-validation enhanced the reliability of hyperparam-
eter tuning and ensured fairness in model evaluation, leading to robust and consistent
results. As reected in both Tables
7and8and their corresponding visual summaries
in Figures3and4, the SVM Polynomial model demonstrated the most consistent
and accurate performance across all frequency domains, making it a reliable option
for traders seeking dependable predictions over varying time horizons.
## 4 Conclusions
This study proposed a comprehensive machine learning-based framework to predict
the directional movement (upward or downward) of two major crude oil benchmarks,
## 18

Fig. 4Heatmap of accuracy measures of predicting the direction movement (up or down) of Brent
daily closing prices across three frequency horizons (daily, weekly, and monthly).
WTI and Brent, across three distinct time horizons: daily, weekly,and monthly. To
this end, six supervised machine learning (ML) classiers, suchas SVM with linear,
polynomial, and RBF kernels, ANN, KNN, DT, RF, and NB, were trained using a rich
set of seventeen technical indicators derived from historical open,high, low, close, and
volume data. To ensure eective feature selection and avoid dimensionality bias, RF
feature importance scores were computed. It can be seen from Figure
2that the feature
score of all the technical indicators is valid. This analysis shows thatall the technical
indicators were found to contribute meaningfully to prediction and thus were retained
for model training. The data was split chronologically using an 80-20 training-test
approach, preserving the time series structure. To standardize model tting, a grid
search with 5-fold time series cross-validation was applied for hyperparameter tuning.
Values of dierent hyperparameters for each model have been presented in Tables5,
and6both for WTI and Brent oil across three time domains such as daily, weekly,
and monthly. Model evaluation was conducted using multiple accuracy metrics: F1-
score, precision, accuracy, and recall. Empirical results, summarized in Tables7and
8, demonstrate that SVM classiers particularly those with linear and polynomial
kernels consistently outperformed other models in most frequency domains. For WTI
prices, SVM Polynomial showed strong performance on both daily and weekly scales,
achieving an F1-score of 0.670 and 0.720, respectively. Likewise, for Brent oil, SVM
Polynomial delivered superior performance across all three frequencies, achieving F1-
scores of 0.679 (daily), 0.682 (weekly), and 0.667 (monthly), with particularly strong
Recall scores, indicating its ability to capture upward or downward movements reli-
ably. ANN and RF models also showed moderate eectiveness but generally lagged
behind SVM-based models. From an investment perspective, the proposed model can
serve as a robust decision support tool. Investors and traders can utilize the directional
prediction output to time their buy/sell decisions more strategically: Buy signals can
## 19

be aligned with predicted upward movements (positive class), Sell or shorting actions
can follow predicted downward movements (negative class). High recall values, espe-
cially from SVM Polynomial and Decision Tree models, imply that the models are
eective in capturing true upward trends crucial for momentum-based strategies. Con-
versely, high precision values indicate a lower rate of false positives, reducing the risk
of making premature or misinformed trades. Furthermore, the research questions that
have been stated at the end of the introduction section have been answered after
completing the analysis. The rst question is
## •
“Can supervised machine learning algorithms eectively predict the directional
movement (increase or decrease) of WTI and Brent crude oil prices?”
Yes, the results demonstrate that supervised machine learning algorithms can eec-
tively predict the directional movement of both WTI and Brent crude oil prices,
especially at daily and weekly frequencies. Although classication accuracy does not
exceed 60–70% consistently, the F1 scores, recall, and precision valuesindicate that
the models are capable of capturing meaningful directional signals in the price data.
For WTI, the highest F1 score reaches 0.720 (SVM Polynomial, weekly), with recall
= 1.000, indicating perfect ability to detect upward movement at that frequency. For
Brent, the highest F1 score is 0.679 (daily) and 0.682 (weekly), both achieved by SVM
Polynomial, with high recall values (0.954 and 0.962, respectively). This performance
suggests that these models can be used for binary trading decisions (buy/sell) with
reasonably good condence, especially in short-term trading contexts.
## •
The second question that we stated that “Among the classiers SVM, ANN, KNN,
Decision Trees, Na ̈ıve Bayes, and Random Forest which model delivers the highest
accuracy and the most balanced performance across multiple evaluation metrics?”
Based on the F1 score, precision, accuracy, and recall, the SVM classier with polyno-
mial kernel consistently delivers the best and most balanced performance across both
benchmarks and all time frequencies. The nal question that needs to be answered
after completing the analysis is
## •
“How does model performance dier between the WTI and Brent benchmarks, and
are there consistent patterns indicating the superiority of a particular algorithm?”
Yes, the comparison of WTI and Brent model results reveals both dierences and con-
sistent performance patterns. Brent’s predictions generally show slightly better overall
performance, particularly in terms of recall and accuracy at the monthlyfrequency. For
example, in the monthly forecasts using the SVM Polynomial model, Brent achieved
an F1 score of 0.667, a recall of 1.000, and an accuracy of 0.706, while WTI reached
an F1 score of 0.564, a recall of 0.733, and an accuracy of 0.452. Although DT and
RF models showed stronger results in some WTI weekly cases, theirperformance was
not consistent across the Brent dataset. Despite these benchmark-specic variations, a
clear and consistent pattern emerges regarding the superiority of the SVM Polynomial
model. It consistently ranks as the top-performing algorithm across both WTI and
Brent benchmarks in all three frequency domains such as daily, weekly, and monthly.
The model achieves the highest F1 scores, strong recall values (often exceeding 0.90 or
## 20

even reaching 1.00), and competitive accuracy levels. These high recall values make it
particularly eective in identifying upward price movements,which is highly valuable
for guiding investment decisions. Although there are minor dierences in model perfor-
mance between WTI and Brent, the SVM with polynomial kernel demonstrates robust
generalizability and consistently superior performance in predicting the directional
movement of crude oil prices across dierent time horizons. To conclude, this research
study utilized various supervised machine learning techniqueswith 17 dierent tech-
nical indicators as input features to predict the directional movement (up or down) of
two major crude oil benchmarks, WTI and Brent, across three time domains—daily,
weekly, and monthly. In the majority of cases for both crude oil types,the SVM
model with a polynomial kernel outperformed the other models, withall models tuned
uniformly using the Grid Search with time series cross-validation(GridSearchTSCV)
approach.
5 Limitation of the Study
A limitation of this study is that we employed only a single method forboth feature
selection and hyperparameter tuning. Specically, we used Random Forest feature
importance to rank and select features and Grid Search with 5-fold timeseries cross-
validation for hyperparameter optimization. While these methods are widely used and
eective, there exist several alternative approaches that may enhance model perfor-
mance and robustness. For feature selection, methods such as Lasso regularization and
mutual information-based selection could be explored. Similarly, forhyperparameter
tuning, more advanced techniques such as Bayesian optimization, randomsearch, or
genetic algorithms could oer better eciency and accuracy in large parameter spaces.
In future research, we aim to investigate these methods by employing a broader set of
feature selection and tuning strategies. Additionally, we plan to extend this work by
predicting the spot prices of both WTI and Brent crude oil using a more comprehen-
sive set of technical indicators, which may further improve predictive accuracy and
practical applicability.
## Declarations
## •
Ethics approval and consent to participateNot applicable.
## •
Consent for publicationNot Applicable
## •
Availability of data and materialsAll the data sets used in this study are avail-
abel in the publically availalbe repository https://www.kaggle.com/muhammadai
## •
Competing interestsThe authors declare no competing interests.
## •
FundingThis research received external funding from the Deanship of Graduate
Studies and Scientic Research at Qassim University (QU-APC-2025).
## •
Author contributionConceptualization, M.A. and M.Ah.; methodology, M.A.
and B.A.; software, M.A.; validation, M.Ah.; formal analysis, M.Ah.; investigation,
B.A.; resources, B.A.; data curation, M.A.; writing—original draft preparation,
M.Ah.; writing—review and editing, B.A.; visualization, M.A.; supervision, B.A.;
project administration, B.A. All the authors have read and agreed to the published
version of the manuscript.
## 21

Acknowledgements.The authors acknowledge and appreciate the Ongoing
Research Funding Program (QU-APC-2025), Qassim University, Buraydah 51452,
## Saudi Arabia
## References
[1] Hamilton, J.D.: Oil and the macroeconomy since world war ii. J. Polit.Econ.
## 91(2), 228–248 (1983)
[2] Alquist, A., Kilian, L.: What do we learn from the price of crude oil futures? J.
## Appl. Econom.25(4), 539–573 (2010)
[3] Kilian, N., Park, C.: The impact of oil price shocks on the u.s. stock market. Int.
## Econ. Rev.50(4), 1267–1287 (2009)
[4] Leung, M.T., Daouk, H., Chen, A.S.: Forecasting stock indices: A comparison of
classication and level estimation models. Int. J. Forecast.16(2), 173–190 (2000)
[5] Box, G.E.P., Jenkins, G.M., Reinsel, G.C.: Time Series Analysis: Forecasting and
Control, 4th edn. Wiley, Hoboken, NJ, USA (2008)
[6] Bollerslev, T.: Generalized autoregressive conditional heteroskedasticity. J.
## Econom.31(3), 307–327 (1986)
[7] Engle, R.F.: Autoregressive conditional heteroscedasticity withestimates of the
variance of united kingdom ination. Econometrica50(4), 987–1008 (1982)
[8] Makridakis, S., Spiliotis, E., Assimakopoulos, V.: Statistical and machine learning
forecasting methods: Concerns and ways forward. PLOS ONE13(3), 0194889
## (2018)
[9] Ali, M., Khan, D., Aamir, M., Ali, A., Ahmad, Z.: Predicting the direction move-
ment of nancial time series using articial neural network and support vector
machine. Complexity13(2021)
[10] Hastie, T., Tibshirani, R., Friedman, J.: The Elements of Statistical Learning,
2nd edn. Springer, New York, NY, USA (2009)
[11] Mehrotra, K.G., Mohan, C.K., Ranka, S.: Elements of Articial Neural Networks.
MIT Press, Cambridge, MA, USA (1997)
[12] Hassan, A.E., Hassan, M.F., Younis, S.: Application of machine learning in pre-
dicting crude oil prices. Energy Sources Part B: Econ. Plan. Policy17(3), 208–218
## (2022)
[13] Atsalakis, C., Valavanis, K.P.: Surveying stock market forecasting techniques –
part ii: Soft computing methods. Expert Syst. Appl.36(3), 5932–5941 (2009)
## 22

[14] Zhang, T., Wu, C., Li, Y.: Oil price shocks and stock markets: Evidence from
china and u.s. Energy Econ.34(6), 1717–1726 (2012)
[15] Rehman, M.S., Iqbal, H., Usman, M.: A comparative study of machine learning
techniques for crude oil price forecasting. J. Petrol. Sci. Eng.208, 109413 (2022)
[16] Huang, P., Ni, Y., Day, M.Y., Chen, Y.: Enhancing investment protability: Study
on contrarian technical strategies in brent crude oil markets. Energies18(11),
## 2735 (2025)
[17] Wen, D., He, M., Liu, L., Zhang, Y.: Forecasting crude oil prices: Do technical
indicators need economic constraints? Quant. Finance22(8), 1545–1559 (2022)
[18] Sodha, M.,et al.: Towards precision: A comparative analysis of crude oil price
forecasting approaches. In: Proc. Int. Conf. Machine Intelligence,Tools, and
Applications, pp. 140–151. Springer, Cham, Switzerland (2024)
[19] Stasiak, M.D., Staszak,
## ̇
Z., Stawarz, M.: Forecasting crude oil prices using the
binary rsi (brsi) indicator. Energies18(12), 3034 (2025)
[20] Zhang, Y., Wang, J., Wang, J.: Oil price forecasting using a hybrid model. Energy
## 160, 854–865 (2018)
[21] Zhang, Y., Wang, J., Wang, J.: A new hybrid deep learning model for monthly
oil prices forecasting. Energy Econ.118, 106518 (2023)
[22] Fang, Y., Wang, W., Wu, P., Zhao, Y.: A sentiment-enhanced hybrid model for
crude oil price forecasting. Expert Syst. Appl.215, 119329 (2023)
[23] Manickavasagam, J., Visalakshmi, S., Apergis, N.: A novel hybrid approach to
forecast crude oil futures using intraday data. Technol. Forecast. Soc. Change
## 158, 120126 (2020)
[24] Khashei, M., Heidari, S., Bijari, M.: A novel hybrid model for crude oil price
forecasting using machine learning and decomposition techniques. Energy Econ.
## 85, 104567 (2020)
[25] Guo, L., Huang, X., Li, Y., Li, H.: Forecasting crude oil futures price using
machine learning methods: Evidence from china. Energy Econ.127, 107089
## (2023)
[26] Hinphy, A.: Predicting WTI crude oil returns using machine learning: A com-
parative study of ensemble and deep learning models. [Online]. Available:
fsc.stevens.edu (2023)
[27] Li, X., Shang, W., Wang, S.: Text-based crude oil price forecasting: A deep
learning approach. Int. J. Forecast.35(4), 1548–1560 (2019)
## 23

[28] Chen, Y., He, K., Tso, G.K.: Forecasting crude oil prices: A deep learning based
model. Procedia Comput. Sci.122, 300–307 (2017)
[29] Li, Y., Yang, Y., Sun, S., Guo, J.: A new hybrid  approach for crude
oil  price  forecasting:  Evidence  from  multi-scale  data.  [Online].  Available:
arxiv.org/abs/2002.09656 (2020)
[30] Investing.com: Financial markets worldwide. [Online]. Accessed: May 24, 2024
[31] Achelis, S.B.: Technical Analysis from A to Z. McGraw-Hill, New York, NY, USA
## (2001)
[32] Lantz, B.: Machine Learning with R: Expert Techniques for Predictive Modeling.
Packt Publishing, Birmingham, U.K. (2019)
[33] McCulloch, W.S., Pitts, W.: A logical calculus of the ideas immanent in nervous
activity. Bull. Math. Biol.52, 99–115 (1990)
[34] Breiman, L.: Random forests. Mach. Learn.45, 5–32 (2001)
[35] Dietterich, T.G.: An experimental comparison of three methods for constructing
ensembles of decision trees: Bagging, boosting, and randomization. Mach. Learn.
## 40, 139–157 (2000)
[36] Frank, E., Trigg, L., Holmes, G., Witten, I.H.: Naive bayes for regression. Mach.
## Learn.41, 5–25 (2000)
[37] Fix, E., Hodges, J.L.: Nonparametric discrimination: Consistency properties.
## Randolph Field, Texas Project (1951)
[38] Prasartvit, T., Banharnsakun, A., Kaewkamnerdpong, B., Achalakul, T.:Reduc-
ing bioinformatics data dimension with abc-knn. Neurocomputing116, 367–381
## (2013)
[39] Zhang, Y.,et  al.: An optimization system for intent recognition based on an
improved knn algorithm with minimal feature set for powered knee prosthesis. J.
## Bionic Eng.20(6), 2619–2632 (2023)
[40] Eman, M., Mahmoud, T.M., Ibrahim, M.M., Abd El-Hafeez, T.: Innovative
hybrid approach for masked face recognition using pretrained mask detection and
segmentation, robust pca, and knn classier. Sensors23(15), 6727 (2023)
[41] Adeniyi, D.A., Wei, Z., Yongquan, Y.: Automated web usage data mining and
recommendation system using k-nearest neighbor (knn) classicationmethod.
## Appl. Comput. Inform.12(1), 90–108 (2016)
[42] Vapnik, V.N.: The Nature of Statistical Learning Theory. Springer, Berlin,
## Germany (1995)
## 24

[43] Rumelhart, D.E., Hinton, G.E., Williams, R.J.: Learning representations by
backpropagating errors. Nature323(6088), 533–536 (1986)
## 25