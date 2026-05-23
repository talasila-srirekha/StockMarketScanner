"""
 You are expert in US Stock analysis. Create a python program that meet the criteria mentioned below for S&P 500 stocks
 Abs (  Daily High -  Daily Low ) >  Abs (  1 day ago High -  1 day ago Low )
 Abs (  Daily High -  Daily Low ) >  Abs (  2 days ago High -  2 days ago Low )
 Abs (  Daily High -  Daily Low ) >  Abs (  3 days ago High -  3 days ago Low )
 Abs (  Daily High -  Daily Low ) >  Abs (  4 days ago High -  4 days ago Low )

 Daily Close >  Daily Open
 Daily Close >  Weekly Open
 Daily Close >  Monthly Open
 Daily Volume *  Daily Close >=  10000000
 Daily Low >  1 day ago Close -  Abs (  1 day ago Close /  222 )
 RSI > 60

Also Analyze the stock pattern for above results and suggest both entry and stop loss and target prices . Display the results in table format with stock information, entry,stoploss and target prices , current volumes and volumes increase /decrease percentage from last 10 days or 1 month
"""