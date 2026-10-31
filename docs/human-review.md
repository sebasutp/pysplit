# Human review

## Round 1

I still didn't test the offline part or the AI help. 

* Please update the README with an example on how to set up the AI to work for receipt parsing (ex: using Gemini or Deepseek API KEYS). If there is a different way to do it in dev than in prod, please explain that. I was thinking we could have a flag to mock an API response with some made up items of a restaurant bill to test locally.

Here are my first thoughts:

### Receipt/Document upload

* If I upload a receipt I can't see it in the UI. I would like to see a small view of the receipt that I can then click to see full screen if I want to.
* The document upload is counter-intuitive to me. It seems like you can only upload images, unlike the receipt part the images upload full resolution instead of being compressed, and you can't do much with it later on. To see it I need to click open and see it in a separate window.

What would be better:

* I don't see a reason to have documents and receipts as separate concepts. If there are please let me know. I think PDFs should also be allowed as attachments.
* The user should be able to either upload a receipt to create the expense (as it is supposed to happen now), or create first the expense and then upload a receipt and have a button to process it with AI.

### Other UI issues

* In activity I see "created by Someone" even though I am logged in. In spliit, when I user enters a group for the first time the app asks it which user he/she is and uses that from then on to identify the user.
* If "Information is empty", it should not show up in the tabs.
* The UI says made in Montreal. But this was made in Zurich/Switzerland by Sebastian Gomez.


## Round 2

### AI Recept processing

* It seems like I have to save the receipt first before I can see the items when successfully processed by the mock AI
* Change the name from "Review items" to "Assign items" and make it visible also near the "Advances split options" button
* When I click "Assign to" in an item and select 2 people I get an error "Could not save your change - Attachment not found"
* After the user clicks "Apply to expense" the user should be taken back automatically to the previous screen
* It seems that the itemized AI summary is being deleted sometimes for some weird reason. I processed one item successfully, then got an error assigning an item to 2 people and when I looked again the attachment had disappeared.
* I see errors in the dev console:
  - Uncaught TypeError: Cannot read properties of undefined (reading 'startTime')
