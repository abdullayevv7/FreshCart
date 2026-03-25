/**
 * Shopping cart drawer component for FreshCart.
 *
 * Slides in from the right side of the screen to show the current cart
 * contents. Supports quantity adjustment, item removal, and checkout.
 */

import { useSelector, useDispatch } from "react-redux";
import { Link } from "react-router-dom";
import { FiX, FiMinus, FiPlus, FiTrash2, FiShoppingBag } from "react-icons/fi";
import {
  selectCartItems,
  selectCartItemCount,
  selectCartSubtotal,
  selectCartStoreName,
  updateQuantity,
  removeFromCart,
  clearCart,
} from "../../store/cartSlice";
import { formatCurrency } from "../../utils/formatters";

export default function CartDrawer({ isOpen, onClose }) {
  const dispatch = useDispatch();
  const items = useSelector(selectCartItems);
  const itemCount = useSelector(selectCartItemCount);
  const subtotal = useSelector(selectCartSubtotal);
  const storeName = useSelector(selectCartStoreName);

  if (!isOpen) return null;

  const handleQuantityChange = (productId, variantId, newQuantity) => {
    if (newQuantity <= 0) {
      dispatch(removeFromCart({ productId, variantId }));
    } else {
      dispatch(updateQuantity({ productId, variantId, quantity: newQuantity }));
    }
  };

  const handleRemoveItem = (productId, variantId) => {
    dispatch(removeFromCart({ productId, variantId }));
  };

  const handleClearCart = () => {
    if (window.confirm("Are you sure you want to clear your cart?")) {
      dispatch(clearCart());
    }
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/30 z-40 transition-opacity"
        onClick={onClose}
      />

      {/* Drawer panel */}
      <div className="fixed right-0 top-0 h-full w-full max-w-md bg-white shadow-xl z-50 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-100">
          <div>
            <h2 className="text-lg font-semibold text-gray-800">
              Your Cart
            </h2>
            {storeName && (
              <p className="text-sm text-gray-500">From {storeName}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 transition-colors"
          >
            <FiX className="w-5 h-5" />
          </button>
        </div>

        {/* Cart contents */}
        {items.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8">
            <FiShoppingBag className="w-16 h-16 text-gray-200 mb-4" />
            <h3 className="text-lg font-medium text-gray-600 mb-2">
              Your cart is empty
            </h3>
            <p className="text-sm text-gray-400 mb-6">
              Browse our stores and add some fresh groceries!
            </p>
            <Link
              to="/stores"
              onClick={onClose}
              className="bg-green-600 text-white px-6 py-2 rounded-lg hover:bg-green-700 transition-colors text-sm font-medium"
            >
              Browse Stores
            </Link>
          </div>
        ) : (
          <>
            {/* Items list */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {items.map((item) => {
                const price = item.variant
                  ? parseFloat(item.variant.price)
                  : parseFloat(item.product.price);
                const itemTotal = price * item.quantity;

                return (
                  <div
                    key={`${item.product.id}-${item.variant?.id || "base"}`}
                    className="flex gap-3 bg-gray-50 rounded-lg p-3"
                  >
                    {/* Image */}
                    <div className="w-16 h-16 rounded-lg overflow-hidden bg-white flex-shrink-0">
                      {item.product.image ? (
                        <img
                          src={item.product.image}
                          alt={item.product.name}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-gray-300">
                          <FiShoppingBag className="w-6 h-6" />
                        </div>
                      )}
                    </div>

                    {/* Details */}
                    <div className="flex-1 min-w-0">
                      <h4 className="text-sm font-medium text-gray-800 truncate">
                        {item.product.name}
                      </h4>
                      {item.variant && (
                        <span className="text-xs text-gray-500">
                          {item.variant.name}
                        </span>
                      )}
                      <p className="text-sm font-semibold text-gray-900 mt-1">
                        {formatCurrency(itemTotal)}
                      </p>

                      {/* Quantity controls */}
                      <div className="flex items-center gap-2 mt-2">
                        <button
                          onClick={() =>
                            handleQuantityChange(
                              item.product.id,
                              item.variant?.id,
                              item.quantity - 1,
                            )
                          }
                          className="w-7 h-7 rounded-full border border-gray-300 flex items-center justify-center text-gray-500 hover:bg-gray-100"
                        >
                          <FiMinus className="w-3 h-3" />
                        </button>
                        <span className="text-sm font-medium w-6 text-center">
                          {item.quantity}
                        </span>
                        <button
                          onClick={() =>
                            handleQuantityChange(
                              item.product.id,
                              item.variant?.id,
                              item.quantity + 1,
                            )
                          }
                          disabled={
                            item.quantity >= item.product.max_order_quantity
                          }
                          className="w-7 h-7 rounded-full border border-gray-300 flex items-center justify-center text-gray-500 hover:bg-gray-100 disabled:opacity-50"
                        >
                          <FiPlus className="w-3 h-3" />
                        </button>

                        <button
                          onClick={() =>
                            handleRemoveItem(
                              item.product.id,
                              item.variant?.id,
                            )
                          }
                          className="ml-auto p-1 text-red-400 hover:text-red-600"
                        >
                          <FiTrash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Footer */}
            <div className="border-t border-gray-100 p-4 space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">
                  Subtotal ({itemCount} items)
                </span>
                <span className="font-semibold text-gray-800">
                  {formatCurrency(subtotal)}
                </span>
              </div>
              <p className="text-xs text-gray-400">
                Delivery fee and taxes calculated at checkout
              </p>
              <Link
                to="/checkout"
                onClick={onClose}
                className="block w-full bg-green-600 text-white text-center py-3 rounded-lg hover:bg-green-700 transition-colors font-medium"
              >
                Proceed to Checkout
              </Link>
              <button
                onClick={handleClearCart}
                className="block w-full text-center text-sm text-red-500 hover:text-red-700 transition-colors"
              >
                Clear Cart
              </button>
            </div>
          </>
        )}
      </div>
    </>
  );
}
