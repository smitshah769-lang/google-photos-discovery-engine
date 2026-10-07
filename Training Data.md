**Training / labeling reference (research v1)** — Taxonomy and sentiment rules below feed **dashboard charts** and **RAG illustrative quotes** (e.g. sentiment questions pull one negative and one neutral/positive labeled example that mention search). RAG does not retrain models on this markdown file; it uses frozen labels in SQLite.

**Overall Sentiment analysis for search function**

| Sentiment | Evidences to consider | Examples from scraped data |
| :---- | :---- | :---- |
| Positive | 1\) Users explicitly mention finding the photo/content they were looking for 2\) Users say search mostly returns relevant or accurate results. 3\) Users highlight that searching photos is intuitive, fast, or easy  | “Great app\! I can find photos of specific people, specific years, or documents\! its great\!” |
|  |  | “I was impressed recently with all the improvements you did to search. seems like now you surface photos from shared albums as well. also you added back the chronological order for search results.” |
| Negative | 1\) Users explicitly mention being unable to find the photo/content they were looking for 2\) Users say search frequently returns irrelevant, inaccurate, or incomplete results. 3\) Users describe searching photos as unintuitive, slow, difficult, or requiring excessive effort. | “it's horrible. It's my default \*gallary" app and managing what's on my device and what's on the cloud is awful. I can't find half the photos I want to send to people.” |
|  |  | “Basic functions are missing Search often w/ wrong results. cannot sort results, so with nonsensical results can be hundreds of images to scroll, plus selecting, starting over each time.” |
| Neutral | 1\) Users describe their experience with search without expressing clear satisfaction or dissatisfaction. 2\) Users discuss how search works or how they use it without expressing a clear positive or negative sentiment. | “Helpful hack: How I manually tag unrecognized people in my photos Google Photos does not currently allow manually tagging faces and frequently can't find some faces on the pictures.” |
|  |  | How to find recent collage that are not saved? Google photo notified me of a collage it made with recent pictures. I didn't save it immediately and I can't find it anymore anywhere. |

**Exploration signal mix** (Note: *to tag the pain points*)

| Type of Signal | Evidences to consider | Examples from scraped data |
| :---- | :---- | ----- |
| No signal | 1\) Overall opinion given with no pain point or problem faced mentioned 2\) Responses involving a solution/questions to a reddit or google community forum post  | “I can't ever find my pictures\!” |
|  |  | “Doesn't sound particularly serious after reading your subsequent posts. Find them and put them in an album called pictures of myself. Good luck.” |
| Actionable Signal | Reviews/Posts/comments which involves a specific problem, pain point, user need or failure point | “How to search for group photos? I searched this question but no one seems to have asked Searching for "group photos" or "group" in the search bar did not filter out the results I wanted: at least four or five people are in the same photo with their faces facing the camera.” |
|  |  | “Too many problems to list. Even the most basic functions don't work. For example search for a photo by filename, it will not find it and instead show you dozens and dozens of files not with that name” |

**User pain points** 

| Overarching Theme | Evidences to consider | Examples from scraped data |
| ----- | ----- | ----- |
| Design Issues | 1\) Difficulty in understanding and navigating the UI to find photos  2\) UI changes, with users preferring the older/previous search functionality  | “The "more like this" search function on individual photos is nowhere to be found. Where did it go?” |
|  |  | “where is the search button after the recent update ? I can't find it anywhere ... google website docs page say "At the bottom, tap Search." , where I see 4 buttons: Photos , Collections, Create , Ask.” |
|  |  | “Date grouping disappeared\! I've been using Google Photos for years but recently an update removed the photos being grouped by date. Makes it much harder to organise and view my photos.” |
| System Issues | 1\) Challenges in searching images due to face not detected/grouped correctly 2\) Challenges in searching images due to incorrect or missing metadata such as place/date/time/file name/device 3\) Challenges in searching images due to object recognition 4\) Challenges in searching images due to other reasons 5\) Bugs/glitches hampering search or finding photos  | “The search option just doesn't work. I'm not even trying to use the function where you describe an image based on how it looks or when/where it was taken which doesn't work at all, I only try searching by the file name or by text that is seen in the image, and it never works.” |
|  |  | “Face search categories are inconsistent, app will separate people into two different profiles or won't acknowledge faces in some photos. Unfortunately still happening” |
|  |  | “Search photo by specific location I want to find all photo I took at specific location with custom radius. Ex: get all photos were took at home. Is there any ways to do that?” |
|  |  | “text search in photos , it's 2026 and we can't serch text in photos, update it like iPhone” |
|  |  | “Is there a way to find similar photos in your library? Basically what the title says, I have a two screenshots of the photo, I have a cropped one that’s square because of Instagram and another full size that was originally on my phone’s dimensions.” |
|  |  | “People Album Missing I logged on to Google Photos after a few months away (since September) and I don't have a People album anymore. I can't search by name either.” |
| Query Inference  | 1\) Search feature failing to understand user query | “did you guys nerf the search function.I used to be able to use it to search anything I was looking for..now it says we can't find the search your looking for..I mean I can find it.” |
|  |  | “AI has made this useless With the recent updates I increasingly find if I search for any photos, then issue a follow up query, it will completely ignore the initial search results and describe some random photo from my library that has nothing to do with what I was searching for.” |
| Knowledge and Awareness Gaps | User did not know a search capability/feature existed, or the capability is hidden or undocumented | “Can you search for photos just by their locations “ |
|  |  | “TIL. You can search your images for what they contain I've used Google Vision API to reference photos in the past and add that to EXIF for albums etc. but I didn't know until today when I'm frantically looking for a photo, I just happened to type in search what the photo had (bees).” |

*Note***:** 

* *The themes are not mutually exclusive and a data point may apply to two or more themes*  
* *Create a separate graph for common sub themes based on your analysis*

**Which search types featured the most in posts/comments?**

| Search Type | Examples from scraped data |
| :---- | ----- |
| Search/AI Search | “Lost the ability to search — Search is gone because there’s a Gemini pop-up where the accept/reject buttons don’t fit the screen.” (Tagged when text mentions search bar, search function, search feature, search option, search results, AI search, Ask Photos, or Gemini.) |
| Searching via People and Pets | “Face grouping lost and can't find albums now? Basically I accidentally turned off face grouping like an idiot and lost everything from the beginning. I gave it a day to process them all again when I turned it on and started going through labeling the people.” |
| Searching via Places | “Where's the "Use Map View to See Your Photos on a Map" |
| Searching via Date & Time | “Would love if app layout could go back to monthly sections as photos are so hard to find now that they are all cluttered together which makes the app much harder to use” |
| Searching via Objects | “I can no longer search my photos for people, colors, objects or words (etc). trying to ask Gemini doesn't work and just sends me back to the search page which always yeilds no results.” |
| Searching via Events | “The option to search for photos using name or event is no longer available. It's practically impossible to manually have to search for old pictures anymore” |
| Searching via File type (Videos/screenshots/selfies etc) | “You have a filter to search only for videos but you don't have a filter to search only for photos. Why?\! It seems like an insane product decision. searching for "photos of " does not work either.” |
| Searching via Albums | “Album Disappointment I spent a long, looong time organising my Albums into Alphabetical order so that I could find them quickly. Showed this feature off to others and that got them starting with Google Photos.” |
| Discovering via Memories | “Memories Rock\! Love the memories reels. Hooks me in \- takes me to long lost pictures I would not normally search for. Love it” |
| Other | “On device folder on iOS? Is there any way to see photos on device vs all photos in my Google photos account? On Android, there in a camera folder but I can't find it on ios.” |

*Note***:** 

* *The search functionalities are not mutually exclusive and a data point may apply to two or more themes*  
* *Consider all positive, negative and neutral posts/comments if search type is mentioned*  
* *Exclude responses involving a solution/questions to a reddit or google community forum post*  
* *Skip if the data has no mention of any of the search types* 

**Search Type \- Sentiment Analysis**

*Note:*

* *For each search type, create a sentiment analysis including positive, negative and neutral posts/reviews*  
* *Exclude responses involving a solution/questions to a reddit or google community forum post*

**Which user suggestions had most upvotes/helpful/likes**

*Note***:** 

* *Surface five snippets and a brief summary*

**Out of Scope/ Filter Out**

| Overaching Theme | Evidence from scraped data |
| ----- | ----- |
| UI related other than for search function | “But I did just discover something \- the edit button is at the bottom for pictures in unshared albums or in the general photo "catch all", but it is not available on photos in albums I have shared, which is what I was looking at earlier- even though they are my albums.” |
|  | “The "export frame" for video is now hard to find and it doesn't even work correctly---it saves a different frame than what you selected. It was fine before, why change it?” |
| Bugs/glitches/technical issues in app other than for search function | “There is a bug in the Creations Module, I've edited a highlight which is getting processed from yesterday (it's stuck). My wifi and internet connection is stable.” |
| Photo sharing only | “Accidently shared photos. How can I undo this? “ |
|  | “Something annoying happened in the recent version\! I usually edit pictures and send them to friends. Now, after I edit them, although I see them in the gallery, when I try to choose from FB or Whatsapp \- I can't find the edited ones at all\!” |
| Data storage and backup only | “I want to get back my permanently deleted data from recycle bin” |
|  | “How can I move photos FROM my Google Photos app TO my device? All my photos are backed up in Photos now. Trouble is, whenever I try to share a photo as, say, a Facebook comment, Facebook doesn't give me that option, it only lets me access my Gallery.” |
|  | “Terribly frustrating, I've switched to a new phone, and the Google Photos App doesn't show any of my old photos and albums. I've tried all of the tips I could find- it's the correct account, when I open it in the browser all my photos are there, I've deactivated the app and activated” |
| Photo Editing | “Getting Worse They have update and taken away the useful editing tools\! I want to keep all my photos on my device\! Can’t find out how to do this\! When there is no signal I can’t see my photos.” |
|  | “why did you have to screw up the magic eraser? there were many features that were great and you add them in and then take them away guess it depends on which Android model you have like if you have the pixel or if you have the \$30 Motorola from Walmart yeah, kind of makes sense, but also it really doesn't.” |
| Privacy & Permissions | “recently, there is an animated "shimmer" over the subject of a photo when you open it. i cannot find a way to turn this off. I can't help but speculate that it's some new ai feature scanning my photos without my consent which feels extremely violating.” |
|  | “Privacy invasive I wanted this for specific features, but did not want to give Google access to every photo on my device. Unfortunately, they disable the ability to upload a single photo unless you give it full access to every photo.” |

*Note*

* *Exclude anything else which is not relevant to what's mentioned in this document*

**Additional Data Points to Keep**

1. Any data points which will help map out user behaviour \- no of photos, recent/old photos, geography, devices etc