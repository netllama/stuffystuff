#!/bin/python2.7
"""Get twitter timeline and convert to XML formatted RSS feed."""

import psycopg2
import psycopg2.extras
import tweepy
import datetime
import pytz
import re
from curses import ascii
from feedgen.feed import FeedGenerator
import sys
reload(sys)
sys.setdefaultencoding('utf8')


CONN_STRING = ''

def main():
    """Main func."""
    # get min/max values from db
    last_id, first_id = max_id()
    if not last_id or not first_id:
    	return

    # get latest tweets
    tweets = get_tweets(last_id)
    if not tweets:
    	# no new tweets
    	return

    # insert new tweets
    insert_worked, tweets_vals = insert_tweets(tweets)
    if not insert_worked:
    	return

    # create xml for rss feed
    feed_built = make_rss_feed(tweets_vals)
    if not feed_built:
    	return

    # delete old tweets
    delete_old_tweets(last_id)


def db_qry(sql_pl, operation):
    """Run specified query."""
    ret_val = True
    sql = sql_pl[0]
    sql_vals = sql_pl[1]
    # connect to database
    try:
        conn = psycopg2.connect(CONN_STRING)
        conn.autocommit = True
    except Exception as err:
        print 'Database connection failed due to error:\t{}'.format(err)
        return False
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    # invoke the SQL
    try:
        cursor.execute(sql, sql_vals)
        row_count = cursor.rowcount
    except Exception as err:
        # query failed
        print 'SQL ( {} )\t failed due to error:\t{}'.format(cursor.query, err)
        ret_val = False
    if operation == 'select' and ret_val:
        # get returned data to return
        ret_val = cursor.fetchall()
    cursor.close()
    conn.close()
    return ret_val


def clean(text):
    """Make string XML compatible by forcing to unicode or ASCII."""
    return str(''.join(
            ascii.isprint(c) and c or '?' for c in text
            ))


def max_id():
    """Get min and max ids from tweets table."""
    last_id = None
    first_id = None
    first_last_sql = 'SELECT min(id), max(id) FROM tweets'
    first_last_qry = db_qry([first_last_sql, None], 'select')
    if not first_last_qry and not first_last_qry[0]:
    	print 'FAILED to get first or last id:\t{}'.format(first_last_qry)
	return last_id, first_id
    last_id = first_last_qry[0][-1]
    first_id = first_last_qry[0][0]
    return last_id, first_id


def oauth_login():
    """Credentials for OAuth."""
    consumer_key = ''
    consumer_secret = ''
    access_token = ''
    access_token_secret = ''

    # Creating the authentication
    auth = tweepy.OAuthHandler(consumer_key,
                               consumer_secret)
    # Twitter instance
    auth.set_access_token(access_token, access_token_secret)
    return tweepy.API(auth)


def get_tweets(last_id):
    """Get tweets from timeline."""
    latest_timeline = []
    tweets = {}
    t_api = oauth_login()
    try:
    	for item in tweepy.Cursor(t_api.home_timeline, since_id=last_id, tweet_mode='extended').items():
    	    latest_timeline.append(item)
    except tweepy.TweepError as err:
    	print 'FAILED to get home_timeline due to error:\t{}'.format(err)
    try:
    	for item in tweepy.Cursor(t_api.mentions_timeline, since_id=last_id, tweet_mode='extended').items():
	    #print '{}\t{}'.format(item.author.screen_name, item.text)
    	    latest_timeline.append(item)
    except tweepy.TweepError as err:
    	print 'FAILED to get mentions_timeline due to error:\t{}'.format(err)
    if latest_timeline:
    	# remove duplicate keys
    	tweets = {t.id_str: t for t in latest_timeline}
    return tweets.values()


def utc_to_local(utc_dt):
    """Convert UTC to local timezone."""
    local_tz = pytz.timezone('America/Los_Angeles')
    local_dt = utc_dt.replace(tzinfo=pytz.utc).astimezone(local_tz)
    # strip off timezone offset, as it confuses the DB
    return local_tz.normalize(local_dt)


def insert_tweets(tweets):
    """Insert new tweets into database."""
    url_regex = 'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    tweets_sql_vals = []
    tweets_payload = []
    for tweet_data in tweets:
    	# convert UTC to localtime
	local_tz = utc_to_local(tweet_data.created_at)
	#print tweet_data.entities['urls']
	if not tweet_data.entities['urls']:
	    # tweet has no explicit URL!?
            # perform regex match for URL
	    # print 'NO URL:\t{}'.format(tweet_data.text)
            urls = re.findall(url_regex, tweet_data.full_text)
            if urls:
                status_url = urls[-1:]
            else:
	        status_url = ['https://twitter.com']
	else:
	    status_url = [tweet_data.entities['urls'][0]['expanded_url']]
	author = tweet_data.author.screen_name
    	tweet_vals = [tweet_data.id_str, local_tz.replace(tzinfo=None),
	    	      author, tweet_data.full_text]
	tweets_sql_vals.append(tweet_vals)
	tweets_payload.append(tweet_vals + status_url)
    insert_sql = 'INSERT INTO tweets (id, tstamp, username, tweet) VALUES (%s, %s, %s, %s)'
    insert_worked = True
    for row in tweets_sql_vals:
    	#print row
    	insert_status = db_qry([insert_sql, row], 'insert')
    	if not insert_status:
	    insert_worked = False
	    print 'Failed to insert:\t{}\t{}'.format(insert_sql, row)
    return insert_worked, tweets_payload


def parse_url(desc):
    """Convert URL into HTML link."""
    new_desc = desc
    desc_list = desc.split(' ')
    if desc_list and desc_list[-1].startswith('http'):
    	url = desc_list[-1]
	html_url = '<A HREF="{u}">{u}</a>'.format(u=url)
	new_desc = desc.replace(url, html_url)
    return u'{}'.format(new_desc)


def make_rss_feed(tweets):
    """Make rss feed."""
    feed_built = True
    fpath = '/var/www/html/tweets.xml'
    tz = pytz.timezone('America/Los_Angeles')
    build_date = datetime.datetime.now(tz)
    fg = FeedGenerator()
    fg.title('netllama twitter')
    fg.link(href='https://www.twitter.com/netllama')
    fg.language('en')
    fg.description('twitter for netllama')
    fg.updated(build_date)
    for tweet in tweets:
    	fe = fg.add_item()
    	fe.guid(tweet[0])
    	# need to re-add TZ info to make this work
    	fe.pubDate(tweet[1].replace(tzinfo=tz))
	#desc = clean(tweet[3])
	#desc = u'{}'.format(tweet[3].encode('utf-8'))
	desc = parse_url(tweet[3].encode('utf-8'))
	# author: desc
	title = u'{}: {}'.format(tweet[2], desc)
    	fe.title(title)
    	fe.description(desc)
    	fe.link(href=tweet[4])
    try:
    	rssfeed = fg.rss_str(pretty=True)
    	fg.rss_file(fpath)
    except Exception as err:
    	print 'Failed to generate RSS feed due to error:\t{}'.format(err)
    	feed_built = False
    return feed_built


def delete_old_tweets(last_id):
    """Delete old tweets."""
    delete_sql = 'DELETE FROM tweets WHERE id < %s AND id NOT IN (SELECT id FROM tweets ORDER BY id DESC LIMIT 15)'
    delete_status = db_qry([delete_sql, [last_id]], 'delete')
    if not delete_status:
    	print 'Failed to delete last_id ({}):\t{}'.format(last_id, delete_sql)


if __name__ == "__main__":
    main()
