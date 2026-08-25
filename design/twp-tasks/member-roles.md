# User Roles

## Admin (NextJs)
Admin role is responsible for Create Read Update Delete of:
* Cultivators 
* Strain listings 
* Finished product types and prices 
* Club/platform rules (don't need a button)

Admin should also be able to:
* disable/remove any user or plant or batch. 
* reverse/refund transactions or part of transaction (transaction/platform fees can be withheld).
* hide a cultivator and its offering
* revoke access.
* cancel memberships.


## Cultivator
Cultivators are able to:
* Manage their profiles
* Primary cultivator profile can appoint other cultivator members with full or limited rights
* upload plant stocks
* manage plant stocks - adjust available plants 
* Manage pricing - including running promo pricing for a defined strain, period, batch or quantity. 
* Manage their own strain listings - CRUD - image, description, available finished product type, price. 
* Sharing members - CRUD, manage stocks 
* Change plant status: preflowering, in bloom, harvested, processed, shipped 
* View and print ownership certificates, packing labels, shipping documents for courier 
* View and respond to reviews and ratings 
* Send requests to admin for listing of new strains and finished product types 
* Record their own notes against users, strains, plants, members subscriptions 
* Submit support requests 

## Member
Members should be able to:
* View and update their profile info and image. 
* Browse available strains and cultivators, including ratings and reviews. 
* Choose and purchase plants with grow services. 
* View their own plant inventory. 
* Enter and browse swap zone, make swaps. 
* Members can also choose to offer their inventory for swap - their plants will then reflect in the swap zone like a sharing member. They could withdraw plants from the swap zone if they choose to. 
* Manage their own inventory through swaps to make sure they don't own more than 4 flowering plants at any one time (system should prompt members to swap flowering plants for pre-flowering plants if needed to keep stock-holding at 4 or fewer. System should prevent swaps if it will cause the member to be overstocked. 
* Rate and review cultivators and plants that they have received. 
* Request support. 
* Track and trace orders. 
* Query orders. 
* Members info should be concealed behind a nickname.


## Sharing Member
Cultivators can register sharing-members - minimum info will be name, ID and nickname.

Cultivators can then allocate 4 flowering plants to each sharing member. This stock will then reflect in the swapzone for members to view and choose as swaps. This is to ensure there is stock in the swap zone to start off.


## Member clarification across roles
Members are buyers - can sign up.

Cultivators are sellers - need to be created by admins.

Cultivators have a primary account and then can give access to staff to manage stock or whatever for the farm, but only the primary can add users and sharing members.

Admin has control over both buyers and sellers.

Sharing member is actually not a role, no login. They are essentially placeholders to keep stock that is already in flower (because that isn’t allowed to be sold) - so essentially a member can buy a seedling, go onto the swapzone and swap it for something that will harvest earlier or even already harvested. So sharing member is to kickstart swapping and let members get product sooner.


